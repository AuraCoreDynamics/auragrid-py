"""Lease client for accessing AuraGrid ILeaseManager via IPC bridge.

Provides both synchronous (``LeaseClient``) and asynchronous
(``AsyncLeaseClient``) clients for managing Cell-Singleton leases
and fencing tokens.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from .ipc import AsyncIpcClient, IpcClient

logger = logging.getLogger("auragrid.lease_client")


@dataclass
class WalMarker:
    """Represents a position in the Write-Ahead Log."""
    topic_id: str
    sequence_number: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WalMarker:
        return cls(
            topic_id=data["topicId"],
            sequence_number=data["sequenceNumber"]
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topicId": self.topic_id,
            "sequenceNumber": self.sequence_number
        }


@dataclass
class LeaseInfo:
    """Lease information for a Cell-Singleton MAS instance."""
    mas_id: str
    holder_node_id: str
    fencing_token: int
    acquired_at: datetime
    expires_at: datetime
    last_known_marker: Optional[WalMarker] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LeaseInfo:
        marker_data = data.get("lastKnownMarker")
        return cls(
            mas_id=data["masId"],
            holder_node_id=data["holderNodeId"],
            fencing_token=data["fencingToken"],
            acquired_at=datetime.fromisoformat(data["acquiredAt"].replace("Z", "+00:00")),
            expires_at=datetime.fromisoformat(data["expiresAt"].replace("Z", "+00:00")),
            last_known_marker=WalMarker.from_dict(marker_data) if marker_data else None
        )


@dataclass
class LeaseAcquisitionResult:
    """Result of attempting to acquire a Cell-Singleton lease."""
    acquired: bool
    lease: Optional[LeaseInfo] = None
    reason: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LeaseAcquisitionResult:
        lease_data = data.get("lease")
        return cls(
            acquired=data["acquired"],
            lease=LeaseInfo.from_dict(lease_data) if lease_data else None,
            reason=data.get("reason")
        )


class LeaseClient:
    """Synchronous lease client backed by IPC bridge."""

    def __init__(self, ipc_client: IpcClient) -> None:
        self._ipc = ipc_client

    def try_acquire_lease(self, mas_id: str, bid: Dict[str, Any]) -> LeaseAcquisitionResult:
        """Attempt to acquire a singleton lease for a MAS."""
        resp = self._ipc.post(
            "/cell/lease/acquire",
            json={"masId": mas_id, "bid": bid}
        )
        resp.raise_for_status()
        return LeaseAcquisitionResult.from_dict(resp.json())

    def renew_lease(self, mas_id: str, fencing_token: int, marker: Optional[WalMarker] = None) -> bool:
        """Renew an existing lease."""
        body = {"masId": mas_id, "fencingToken": fencing_token}
        if marker:
            body["marker"] = marker.to_dict()
            
        resp = self._ipc.post("/cell/lease/renew", json=body)
        resp.raise_for_status()
        return resp.json().get("extended", False)

    def release_lease(self, mas_id: str, fencing_token: int) -> None:
        """Release a lease held by this MAS."""
        resp = self._ipc.post(
            "/cell/lease/release",
            json={"masId": mas_id, "fencingToken": fencing_token}
        )
        resp.raise_for_status()

    def get_lease_info(self, mas_id: str) -> Optional[LeaseInfo]:
        """Get current lease info for a MAS."""
        resp = self._ipc.get(f"/cell/lease/{mas_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return LeaseInfo.from_dict(resp.json())

    def get_last_marker(self, mas_id: str) -> Optional[WalMarker]:
        """Get the last reported WAL marker for a MAS lease."""
        resp = self._ipc.get(f"/cell/lease/marker/{mas_id}")
        resp.raise_for_status()
        marker_data = resp.json().get("marker")
        return WalMarker.from_dict(marker_data) if marker_data else None


class AsyncLeaseClient:
    """Asynchronous lease client backed by IPC bridge."""

    def __init__(self, ipc_client: AsyncIpcClient) -> None:
        self._ipc = ipc_client

    async def try_acquire_lease(self, mas_id: str, bid: Dict[str, Any]) -> LeaseAcquisitionResult:
        """Attempt to acquire a singleton lease for a MAS."""
        resp = await self._ipc.post(
            "/cell/lease/acquire",
            json={"masId": mas_id, "bid": bid}
        )
        resp.raise_for_status()
        return LeaseAcquisitionResult.from_dict(resp.json())

    async def renew_lease(self, mas_id: str, fencing_token: int, marker: Optional[WalMarker] = None) -> bool:
        """Renew an existing lease."""
        body = {"masId": mas_id, "fencingToken": fencing_token}
        if marker:
            body["marker"] = marker.to_dict()
            
        resp = await self._ipc.post("/cell/lease/renew", json=body)
        resp.raise_for_status()
        return resp.json().get("extended", False)

    async def release_lease(self, mas_id: str, fencing_token: int) -> None:
        """Release a lease held by this MAS."""
        resp = await self._ipc.post(
            "/cell/lease/release",
            json={"masId": mas_id, "fencingToken": fencing_token}
        )
        resp.raise_for_status()

    async def get_lease_info(self, mas_id: str) -> Optional[LeaseInfo]:
        """Get current lease info for a MAS."""
        resp = await self._ipc.get(f"/cell/lease/{mas_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return LeaseInfo.from_dict(resp.json())

    async def get_last_marker(self, mas_id: str) -> Optional[WalMarker]:
        """Get the last reported WAL marker for a MAS lease."""
        resp = await self._ipc.get(f"/cell/lease/marker/{mas_id}")
        resp.raise_for_status()
        marker_data = resp.json().get("marker")
        return WalMarker.from_dict(marker_data) if marker_data else None
