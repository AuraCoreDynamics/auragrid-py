"""Tests for CollaborationClient, AsyncCollaborationClient, enterprise fallback, and fencing conflicts."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from auragrid import (
    AsyncCollaborationClient,
    AsyncGridContext,
    CollaborationClient,
    ConflictError,
    ConflictResolutionAction,
    GridContext,
    LeaseConflictDto,
    LeaseRecordDto,
    MasPlacementMode,
    WorkBatchClaimDto,
)
from auragrid.ipc import AsyncIpcClient, IpcClient, IpcOptions

from .conftest import make_json_response


def _make_sync_collab(handler: Any, ipc_options: IpcOptions) -> tuple[IpcClient, CollaborationClient]:
    ipc_options.max_retries = 0
    client = IpcClient(ipc_options)
    client._client = httpx.Client(
        base_url=ipc_options.base_url,
        headers={"Accept": "application/json", "X-AuraGrid-IPC-Token": ipc_options.token},
        timeout=ipc_options.timeout,
        transport=httpx.MockTransport(handler),
    )
    return ipc_client_pair(client, CollaborationClient(client))


def ipc_client_pair(ipc_client: Any, collab: Any) -> tuple[Any, Any]:
    return ipc_client, collab


def _make_async_collab(handler: Any, ipc_options: IpcOptions) -> tuple[AsyncIpcClient, AsyncCollaborationClient]:
    ipc_options.max_retries = 0
    client = AsyncIpcClient(ipc_options)
    client._client = httpx.AsyncClient(
        base_url=ipc_options.base_url,
        headers={"Accept": "application/json", "X-AuraGrid-IPC-Token": ipc_options.token},
        timeout=ipc_options.timeout,
        transport=httpx.MockTransport(handler),
    )
    return client, AsyncCollaborationClient(client)


def test_claim_and_commit_batch_with_fencing_token() -> None:
    """Verify batch claiming, staged commit, and ConflictPending detection on stale fencingToken."""
    with GridContext(standalone=True) as ctx:
        assert ctx.collaboration is not None

        initial_status = ctx.collaboration.set_volunteer_enabled("model-indexer", True, user="alice")
        assert isinstance(initial_status, LeaseRecordDto)
        assert initial_status.volunteer_enabled is True
        assert initial_status.state == "Active"
        assert initial_status.mode == MasPlacementMode.CELL_SINGLETON
        valid_token = initial_status.fencing_token

        # 1. Claim and commit a valid batch using the active fencing token
        first_batch = ctx.collaboration.claim_work_batch("model-indexer", ["doc-1", "doc-2"], ttl_seconds=90.0)
        assert isinstance(first_batch, WorkBatchClaimDto)
        assert first_batch.status == "Claimed"
        assert first_batch.item_ids == ["doc-1", "doc-2"]
        assert first_batch.fencing_token == valid_token

        committed = ctx.collaboration.commit_work_batch(
            first_batch.batch_id,
            fencing_token=valid_token,
            checkpoint_metadata={"phase": "indexed"},
        )
        assert committed.status == "Committed"
        assert committed.checkpoint_metadata == {"phase": "indexed"}

        # 2. Simulate fencing token advance (another peer acquired a newer epoch),
        #    while a stale worker attempts to commit with the superseded token.
        stale_batch = ctx.collaboration.claim_work_batch("model-indexer", ["doc-3"], ttl_seconds=60.0)
        stale_token = stale_batch.fencing_token
        assert stale_token is not None

        advanced_status = ctx.collaboration.set_volunteer_enabled("model-indexer", True, user="bob")
        assert advanced_status.fencing_token > stale_token

        with pytest.raises(ConflictError) as exc_info:
            ctx.collaboration.commit_work_batch(stale_batch.batch_id, fencing_token=stale_token)

        assert exc_info.value.status_code == 409
        assert exc_info.value.conflict is not None
        assert exc_info.value.conflict.local_fencing_token == stale_token
        assert exc_info.value.conflict.remote_fencing_token == advanced_status.fencing_token

        # 3. Lease transitions to ConflictPending and lists recoverable conflict options
        conflict_status = ctx.collaboration.get_status("model-indexer")
        assert conflict_status.state == "ConflictPending"

        conflicts = ctx.collaboration.list_conflicts("model-indexer")
        assert len(conflicts) == 1
        assert isinstance(conflicts[0], LeaseConflictDto)
        assert ConflictResolutionAction.TAKE_OVER_STALE_LOCK in conflicts[0].available_resolutions

        resolved = ctx.collaboration.resolve_conflict(
            conflicts[0].conflict_id,
            ConflictResolutionAction.TAKE_OVER_STALE_LOCK,
        )
        assert resolved.state == "Active"
        assert resolved.fencing_token > advanced_status.fencing_token
        assert ctx.collaboration.list_conflicts("model-indexer") == []


def test_enterprise_headless_fallback_404_and_501(ipc_options: IpcOptions) -> None:
    """Verify graceful fallback when running against headless enterprise AuraGrid nodes."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/cell/collaboration/status/router-mas":
            return make_json_response({"message": "Not Found"}, status_code=404)
        if path == "/cell/lease/router-mas":
            return make_json_response(
                {
                    "masId": "router-mas",
                    "holderNodeId": "enterprise-node-1",
                    "fencingToken": 12,
                    "acquiredAt": "2026-11-12T10:00:00Z",
                    "expiresAt": "2026-11-12T10:02:00Z",
                }
            )
        if path == "/cell/collaboration/batches/claim":
            return make_json_response({"message": "Not Implemented"}, status_code=501)
        if path.startswith("/cell/collaboration/batches/") and path.endswith("/commit"):
            return make_json_response({"message": "Not Implemented"}, status_code=501)
        if path == "/cell/collaboration/conflicts":
            return make_json_response({"message": "Not Found"}, status_code=404)
        return make_json_response({}, status_code=404)

    ipc_client, collab = _make_sync_collab(handler, ipc_options)
    try:
        status = collab.get_status("router-mas")
        assert status.mas_id == "router-mas"
        assert status.holder_node_id == "enterprise-node-1"
        assert status.fencing_token == 12
        assert status.mode == MasPlacementMode.CELL_SINGLETON

        batch = collab.claim_work_batch("router-mas", ["item-a", "item-b"])
        assert batch.batch_id.startswith("local-")
        assert batch.status == "Claimed"
        assert batch.item_ids == ["item-a", "item-b"]

        committed = collab.commit_work_batch(batch.batch_id, fencing_token=12)
        assert committed.status == "Committed"

        assert collab.list_conflicts("router-mas") == []
    finally:
        ipc_client.close()


@pytest.mark.asyncio
async def test_async_collaboration_emulated_flow() -> None:
    """Verify AsyncGridContext.collaboration end-to-end in standalone emulation."""
    async with AsyncGridContext(standalone=True) as ctx:
        rec = await ctx.collaboration.set_volunteer_enabled("async-mas", True, user="alice")
        assert rec.volunteer_enabled is True
        batch = await ctx.collaboration.claim_work_batch("async-mas", ["w1", "w2"])
        committed = await ctx.collaboration.commit_work_batch(batch.batch_id, rec.fencing_token)
        assert committed.status == "Committed"
        fetched = await ctx.collaboration.get_status("async-mas")
        assert fetched.mas_id == "async-mas"


@pytest.mark.asyncio
async def test_async_collaboration_conflict_409_via_http(ipc_options: IpcOptions) -> None:
    """Verify AsyncCollaborationClient parses HTTP 409 LeaseConflictDto payload into ConflictError."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cell/collaboration/batches/b-99/commit":
            body = json.loads(request.content)
            assert body["fencingToken"] == 4
            return make_json_response(
                {
                    "conflictId": "c-99",
                    "masId": "sync-worker",
                    "localNodeId": "node-a",
                    "localFencingToken": 4,
                    "remoteHolderNodeId": "node-b",
                    "remoteHolderUser": "bob",
                    "remoteFencingToken": 5,
                    "uncommittedItemCount": 2,
                    "detectedAtUtc": "2026-11-12T10:15:00Z",
                    "availableResolutions": ["DiscardLocalAndSync", "YieldToPeer"],
                },
                status_code=409,
            )
        return make_json_response({}, status_code=404)

    ipc_client, collab = _make_async_collab(handler, ipc_options)
    try:
        with pytest.raises(ConflictError) as exc_info:
            await collab.commit_work_batch("b-99", fencing_token=4)
        assert exc_info.value.conflict is not None
        assert exc_info.value.conflict.conflict_id == "c-99"
        assert exc_info.value.conflict.remote_holder_user == "bob"
    finally:
        await ipc_client.close()
