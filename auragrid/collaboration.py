"""Collaborative user-space execution and conflict resolution IPC client.

Provides synchronous (``CollaborationClient``) and asynchronous
(``AsyncCollaborationClient``) clients plus Pydantic DTOs aligned with
``auragrid-api/schemas/lease-collaboration.schema.json`` and
``auragrid-api/openapi/ipc-bridge.openapi.json``.
"""

from __future__ import annotations

import getpass
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from .event_models import WalMarkerDto
from .ipc import AsyncIpcClient, IpcClient, IpcError


class MasPlacementMode(str, Enum):
    """Canonical MAS placement topology modes across AuraGrid and AuraSprout."""

    LOCAL_ONLY = "LocalOnly"
    CELL_SINGLETON = "CellSingleton"
    DISTRIBUTED = "Distributed"


class ConflictResolutionAction(str, Enum):
    """Supported user actions for resolving a stale lease or batch conflict."""

    DISCARD_LOCAL_AND_SYNC = "DiscardLocalAndSync"
    KEEP_LOCAL_AND_STAGE_MERGE = "KeepLocalAndStageMerge"
    TAKE_OVER_STALE_LOCK = "TakeOverStaleLock"
    YIELD_TO_PEER = "YieldToPeer"


class LeaseRecordDto(BaseModel):
    """Extended lease record carrying user-space volunteer and progress state."""

    model_config = ConfigDict(populate_by_name=True)

    mas_id: str = Field(alias="masId")
    mode: MasPlacementMode = Field(default=MasPlacementMode.CELL_SINGLETON, alias="mode")
    holder_node_id: str = Field(alias="holderNodeId")
    holder_user: str = Field(default="", alias="holderUser")
    holder_host_name: str = Field(default="", alias="holderHostName")
    fencing_token: int = Field(alias="fencingToken")
    acquired_at: datetime = Field(alias="acquiredAt")
    expires_at: datetime = Field(alias="expiresAt")
    last_known_marker: Optional[WalMarkerDto] = Field(default=None, alias="lastKnownMarker")
    pid: Optional[int] = Field(default=None, alias="pid")
    volunteer_enabled: bool = Field(default=False, alias="volunteerEnabled")
    activity_summary: Optional[str] = Field(default=None, alias="activitySummary")
    progress_pct: Optional[float] = Field(default=None, alias="progressPct")
    last_checkpoint_utc: Optional[datetime] = Field(default=None, alias="lastCheckpointUtc")
    state: str = Field(default="Active", alias="state")


class WorkBatchClaimDto(BaseModel):
    """Atomic Distributed work-batch claim and commit envelope."""

    model_config = ConfigDict(populate_by_name=True)

    batch_id: str = Field(alias="batchId")
    mas_id: str = Field(alias="masId")
    claimed_by_node_id: str = Field(alias="claimedByNodeId")
    claimed_by_user: str = Field(alias="claimedByUser")
    claimed_at_utc: datetime = Field(alias="claimedAtUtc")
    expires_at_utc: datetime = Field(alias="expiresAtUtc")
    item_ids: list[str] = Field(alias="itemIds")
    status: str = Field(alias="status")
    fencing_token: Optional[int] = Field(default=None, alias="fencingToken")
    checkpoint_metadata: Optional[dict[str, str]] = Field(default=None, alias="checkpointMetadata")


class LeaseConflictDto(BaseModel):
    """Conflict report emitted when a stale fencing token or split-brain write occurs."""

    model_config = ConfigDict(populate_by_name=True)

    conflict_id: str = Field(alias="conflictId")
    mas_id: str = Field(alias="masId")
    local_node_id: str = Field(alias="localNodeId")
    local_fencing_token: int = Field(alias="localFencingToken")
    remote_holder_node_id: str = Field(alias="remoteHolderNodeId")
    remote_holder_user: str = Field(alias="remoteHolderUser")
    remote_fencing_token: int = Field(alias="remoteFencingToken")
    uncommitted_item_count: int = Field(alias="uncommittedItemCount")
    detected_at_utc: datetime = Field(alias="detectedAtUtc")
    available_resolutions: list[ConflictResolutionAction] = Field(alias="availableResolutions")


class ConflictError(IpcError):
    """Raised when a staged work-batch commit fails due to a stale fencing token (HTTP 409)."""

    def __init__(
        self,
        message: str = "Lease or batch conflict detected",
        conflict: Optional[LeaseConflictDto] = None,
    ) -> None:
        super().__init__(409, message, payload=conflict.model_dump(by_alias=True) if conflict else None)
        self.conflict = conflict


def _local_node_identity() -> tuple[str, str, str]:
    node_id = os.environ.get("AURAGRID_NODE_ID") or socket.gethostname() or "local-node"
    user = getpass.getuser()
    host = socket.gethostname() or "localhost"
    return node_id, user, host


def _parse_conflict_from_payload(payload: Any, message: str) -> ConflictError:
    conflict: Optional[LeaseConflictDto] = None
    if isinstance(payload, dict) and "conflictId" in payload:
        conflict = LeaseConflictDto.model_validate(payload)
    return ConflictError(message=message, conflict=conflict)


def _enterprise_passthrough_claim(
    mas_id: str,
    item_ids: list[str],
    ttl_seconds: float,
    status: str = "Claimed",
    batch_id: Optional[str] = None,
    fencing_token: Optional[int] = None,
    checkpoint_metadata: Optional[dict[str, str]] = None,
) -> WorkBatchClaimDto:
    now = datetime.now(timezone.utc)
    node_id, user, _ = _local_node_identity()
    token = fencing_token
    if token is None:
        raw_env = os.environ.get("AURAGRID_FENCING_TOKEN")
        if raw_env and raw_env.isdigit():
            token = int(raw_env)
    return WorkBatchClaimDto(
        batchId=batch_id or f"local-{uuid.uuid4().hex[:12]}",
        masId=mas_id,
        claimedByNodeId=node_id,
        claimedByUser=user,
        claimedAtUtc=now,
        expiresAtUtc=now + timedelta(seconds=ttl_seconds),
        itemIds=list(item_ids),
        status=status,
        fencingToken=token,
        checkpointMetadata=checkpoint_metadata,
    )


class CollaborationClient:
    """Synchronous collaborative execution and lease deconfliction client."""

    def __init__(self, ipc_client: IpcClient) -> None:
        self._ipc = ipc_client

    def get_status(self, mas_id: str) -> LeaseRecordDto:
        """Fetch collaboration lease status, falling back to ``/cell/lease/{mas_id}`` on 404/501."""
        fallback_needed = False
        try:
            resp = self._ipc.get(f"/cell/collaboration/status/{mas_id}")
            if resp.status_code in (404, 501):
                fallback_needed = True
            else:
                resp.raise_for_status()
                return LeaseRecordDto.model_validate(resp.json())
        except IpcError as exc:
            if exc.status_code not in (404, 501):
                raise
            fallback_needed = True

        if fallback_needed:
            resp = self._ipc.get(f"/cell/lease/{mas_id}")
            if resp.status_code >= 400:
                raise IpcError(resp.status_code, resp.text)
            payload = dict(resp.json())
            _, user, host = _local_node_identity()
            payload.setdefault("mode", MasPlacementMode.CELL_SINGLETON.value)
            payload.setdefault("holderUser", user)
            payload.setdefault("holderHostName", host)
            payload.setdefault("volunteerEnabled", True)
            payload.setdefault("state", "Active")
            return LeaseRecordDto.model_validate(payload)
        raise RuntimeError("Unreachable fallback branch")

    def set_volunteer_enabled(
        self,
        mas_id: str,
        enabled: bool,
        user: str | None = None,
    ) -> LeaseRecordDto:
        """Toggle opt-in volunteer participation for a MAS service."""
        body: dict[str, Any] = {"masId": mas_id, "enabled": enabled}
        if user is not None:
            body["user"] = user
        resp = self._ipc.post("/cell/collaboration/volunteer", json=body)
        if resp.status_code >= 400:
            raise IpcError(resp.status_code, resp.text)
        return LeaseRecordDto.model_validate(resp.json())

    def claim_work_batch(
        self,
        mas_id: str,
        item_ids: list[str],
        ttl_seconds: float = 60.0,
    ) -> WorkBatchClaimDto:
        """Atomically claim a Distributed work batch, falling back cleanly on headless enterprise 404/501."""
        body = {
            "masId": mas_id,
            "itemIds": list(item_ids),
            "ttlSeconds": float(ttl_seconds),
        }
        try:
            resp = self._ipc.post("/cell/collaboration/batches/claim", json=body)
            if resp.status_code in (404, 501):
                return _enterprise_passthrough_claim(mas_id, item_ids, ttl_seconds)
            if resp.status_code >= 400:
                raise IpcError(resp.status_code, resp.text)
            return WorkBatchClaimDto.model_validate(resp.json())
        except IpcError as exc:
            if exc.status_code in (404, 501):
                return _enterprise_passthrough_claim(mas_id, item_ids, ttl_seconds)
            raise

    def commit_work_batch(
        self,
        batch_id: str,
        fencing_token: int,
        checkpoint_metadata: dict[str, Any] | None = None,
    ) -> WorkBatchClaimDto:
        """Commit a staged work batch, raising ``ConflictError`` (HTTP 409) on stale fencing token."""
        body: dict[str, Any] = {"fencingToken": int(fencing_token)}
        if checkpoint_metadata is not None:
            body["checkpointMetadata"] = {str(k): str(v) for k, v in checkpoint_metadata.items()}
        try:
            resp = self._ipc.post(f"/cell/collaboration/batches/{batch_id}/commit", json=body)
        except IpcError as exc:
            if exc.status_code == 409:
                raise _parse_conflict_from_payload(exc.payload, exc.message) from exc
            if exc.status_code in (404, 501) and (batch_id.startswith("local-") or exc.status_code == 501):
                return _enterprise_passthrough_claim(
                    mas_id=os.environ.get("AURAGRID_MAS_ID", "local-mas"),
                    item_ids=[],
                    ttl_seconds=60.0,
                    status="Committed",
                    batch_id=batch_id,
                    fencing_token=fencing_token,
                    checkpoint_metadata=body.get("checkpointMetadata"),
                )
            raise

        if resp.status_code == 409:
            raise _parse_conflict_from_payload(resp.json(), resp.text)
        if resp.status_code in (404, 501) and (batch_id.startswith("local-") or resp.status_code == 501):
            return _enterprise_passthrough_claim(
                mas_id=os.environ.get("AURAGRID_MAS_ID", "local-mas"),
                item_ids=[],
                ttl_seconds=60.0,
                status="Committed",
                batch_id=batch_id,
                fencing_token=fencing_token,
                checkpoint_metadata=body.get("checkpointMetadata"),
            )
        if resp.status_code >= 400:
            raise IpcError(resp.status_code, resp.text)
        return WorkBatchClaimDto.model_validate(resp.json())

    def list_conflicts(self, mas_id: str | None = None) -> list[LeaseConflictDto]:
        """List pending lease/batch conflicts requiring user-space resolution."""
        params = {"masId": mas_id} if mas_id is not None else None
        try:
            resp = self._ipc.get("/cell/collaboration/conflicts", params=params)
        except IpcError as exc:
            if exc.status_code in (404, 501):
                return []
            raise

        if resp.status_code in (404, 501):
            return []
        if resp.status_code >= 400:
            raise IpcError(resp.status_code, resp.text)
        data = resp.json()
        raw_list = data.get("conflicts", []) if isinstance(data, dict) else data
        return [LeaseConflictDto.model_validate(item) for item in raw_list]

    def resolve_conflict(
        self,
        conflict_id: str,
        action: Union[ConflictResolutionAction, str],
    ) -> LeaseRecordDto:
        """Resolve a pending lease/batch conflict using an explicit resolution policy."""
        action_val = action.value if isinstance(action, ConflictResolutionAction) else str(action)
        resp = self._ipc.post(
            f"/cell/collaboration/conflicts/{conflict_id}/resolve",
            json={"action": action_val},
        )
        if resp.status_code >= 400:
            raise IpcError(resp.status_code, resp.text)
        return LeaseRecordDto.model_validate(resp.json())


class AsyncCollaborationClient:
    """Asynchronous collaborative execution and lease deconfliction client."""

    def __init__(self, ipc_client: AsyncIpcClient) -> None:
        self._ipc = ipc_client

    async def get_status(self, mas_id: str) -> LeaseRecordDto:
        """Fetch collaboration lease status asynchronously with ``/cell/lease/{mas_id}`` fallback."""
        fallback_needed = False
        try:
            resp = await self._ipc.get(f"/cell/collaboration/status/{mas_id}")
            if resp.status_code in (404, 501):
                fallback_needed = True
            else:
                resp.raise_for_status()
                return LeaseRecordDto.model_validate(resp.json())
        except IpcError as exc:
            if exc.status_code not in (404, 501):
                raise
            fallback_needed = True

        if fallback_needed:
            resp = await self._ipc.get(f"/cell/lease/{mas_id}")
            if resp.status_code >= 400:
                raise IpcError(resp.status_code, resp.text)
            payload = dict(resp.json())
            _, user, host = _local_node_identity()
            payload.setdefault("mode", MasPlacementMode.CELL_SINGLETON.value)
            payload.setdefault("holderUser", user)
            payload.setdefault("holderHostName", host)
            payload.setdefault("volunteerEnabled", True)
            payload.setdefault("state", "Active")
            return LeaseRecordDto.model_validate(payload)
        raise RuntimeError("Unreachable fallback branch")

    async def set_volunteer_enabled(
        self,
        mas_id: str,
        enabled: bool,
        user: str | None = None,
    ) -> LeaseRecordDto:
        """Toggle opt-in volunteer participation asynchronously."""
        body: dict[str, Any] = {"masId": mas_id, "enabled": enabled}
        if user is not None:
            body["user"] = user
        resp = await self._ipc.post("/cell/collaboration/volunteer", json=body)
        if resp.status_code >= 400:
            raise IpcError(resp.status_code, resp.text)
        return LeaseRecordDto.model_validate(resp.json())

    async def claim_work_batch(
        self,
        mas_id: str,
        item_ids: list[str],
        ttl_seconds: float = 60.0,
    ) -> WorkBatchClaimDto:
        """Atomically claim a Distributed work batch asynchronously."""
        body = {
            "masId": mas_id,
            "itemIds": list(item_ids),
            "ttlSeconds": float(ttl_seconds),
        }
        try:
            resp = await self._ipc.post("/cell/collaboration/batches/claim", json=body)
            if resp.status_code in (404, 501):
                return _enterprise_passthrough_claim(mas_id, item_ids, ttl_seconds)
            if resp.status_code >= 400:
                raise IpcError(resp.status_code, resp.text)
            return WorkBatchClaimDto.model_validate(resp.json())
        except IpcError as exc:
            if exc.status_code in (404, 501):
                return _enterprise_passthrough_claim(mas_id, item_ids, ttl_seconds)
            raise

    async def commit_work_batch(
        self,
        batch_id: str,
        fencing_token: int,
        checkpoint_metadata: dict[str, Any] | None = None,
    ) -> WorkBatchClaimDto:
        """Commit a staged work batch asynchronously, raising ``ConflictError`` on stale fencing token."""
        body: dict[str, Any] = {"fencingToken": int(fencing_token)}
        if checkpoint_metadata is not None:
            body["checkpointMetadata"] = {str(k): str(v) for k, v in checkpoint_metadata.items()}
        try:
            resp = await self._ipc.post(f"/cell/collaboration/batches/{batch_id}/commit", json=body)
        except IpcError as exc:
            if exc.status_code == 409:
                raise _parse_conflict_from_payload(exc.payload, exc.message) from exc
            if exc.status_code in (404, 501) and (batch_id.startswith("local-") or exc.status_code == 501):
                return _enterprise_passthrough_claim(
                    mas_id=os.environ.get("AURAGRID_MAS_ID", "local-mas"),
                    item_ids=[],
                    ttl_seconds=60.0,
                    status="Committed",
                    batch_id=batch_id,
                    fencing_token=fencing_token,
                    checkpoint_metadata=body.get("checkpointMetadata"),
                )
            raise

        if resp.status_code == 409:
            raise _parse_conflict_from_payload(resp.json(), resp.text)
        if resp.status_code in (404, 501) and (batch_id.startswith("local-") or resp.status_code == 501):
            return _enterprise_passthrough_claim(
                mas_id=os.environ.get("AURAGRID_MAS_ID", "local-mas"),
                item_ids=[],
                ttl_seconds=60.0,
                status="Committed",
                batch_id=batch_id,
                fencing_token=fencing_token,
                checkpoint_metadata=body.get("checkpointMetadata"),
            )
        if resp.status_code >= 400:
            raise IpcError(resp.status_code, resp.text)
        return WorkBatchClaimDto.model_validate(resp.json())

    async def list_conflicts(self, mas_id: str | None = None) -> list[LeaseConflictDto]:
        """List pending lease/batch conflicts asynchronously."""
        params = {"masId": mas_id} if mas_id is not None else None
        try:
            resp = await self._ipc.get("/cell/collaboration/conflicts", params=params)
        except IpcError as exc:
            if exc.status_code in (404, 501):
                return []
            raise

        if resp.status_code in (404, 501):
            return []
        if resp.status_code >= 400:
            raise IpcError(resp.status_code, resp.text)
        data = resp.json()
        raw_list = data.get("conflicts", []) if isinstance(data, dict) else data
        return [LeaseConflictDto.model_validate(item) for item in raw_list]

    async def resolve_conflict(
        self,
        conflict_id: str,
        action: Union[ConflictResolutionAction, str],
    ) -> LeaseRecordDto:
        """Resolve a pending lease/batch conflict asynchronously."""
        action_val = action.value if isinstance(action, ConflictResolutionAction) else str(action)
        resp = await self._ipc.post(
            f"/cell/collaboration/conflicts/{conflict_id}/resolve",
            json={"action": action_val},
        )
        if resp.status_code >= 400:
            raise IpcError(resp.status_code, resp.text)
        return LeaseRecordDto.model_validate(resp.json())
