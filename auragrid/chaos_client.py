"""Chaos client for injecting faults and testing grid resilience via IPC bridge.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .ipc import AsyncIpcClient, IpcClient

logger = logging.getLogger("auragrid.chaos_client")


@dataclass
class NetworkFaultConfig:
    status_code: Optional[int]
    latency_ms: Optional[int]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NetworkFaultConfig:
        return cls(
            status_code=data.get("statusCode"),
            latency_ms=data.get("latencyMs")
        )


@dataclass
class ChaosStatus:
    gossip_suspended: bool
    storage_fault_enabled: bool
    network_faults: Dict[str, NetworkFaultConfig]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChaosStatus:
        faults = {
            k: NetworkFaultConfig.from_dict(v) 
            for k, v in data.get("networkFaults", {}).items()
        }
        return cls(
            gossip_suspended=data["gossipSuspended"],
            storage_fault_enabled=data["storageFaultEnabled"],
            network_faults=faults
        )


class ChaosClient:
    """Synchronous chaos client backed by IPC bridge."""

    def __init__(self, ipc_client: IpcClient) -> None:
        self._ipc = ipc_client

    def get_status(self) -> ChaosStatus:
        """Get current chaos configuration for this node."""
        resp = self._ipc.get("/cell/chaos/status")
        resp.raise_for_status()
        return ChaosStatus.from_dict(resp.json())

    def suspend_gossip(self, suspended: bool = True) -> None:
        """Suspend or resume SWIM gossip heartbeats."""
        resp = self._ipc.post(
            "/cell/chaos/gossip",
            params={"suspended": str(suspended).lower()}
        )
        resp.raise_for_status()

    def set_network_fault(self, 
                          node_id: Optional[str] = None, 
                          status_code: Optional[int] = None, 
                          latency_ms: Optional[int] = None) -> None:
        """Inject network faults for specific remote nodes."""
        params = {}
        if node_id: params["nodeId"] = node_id
        if status_code: params["statusCode"] = str(status_code)
        if latency_ms: params["latencyMs"] = str(latency_ms)
        
        resp = self._ipc.post("/cell/chaos/network", params=params)
        resp.raise_for_status()

    def set_storage_fault(self, enabled: bool = True) -> None:
        """Enable or disable shared storage mutation faults."""
        resp = self._ipc.post(
            "/cell/chaos/storage",
            params={"enabled": str(enabled).lower()}
        )
        resp.raise_for_status()


class AsyncChaosClient:
    """Asynchronous chaos client backed by IPC bridge."""

    def __init__(self, ipc_client: AsyncIpcClient) -> None:
        self._ipc = ipc_client

    async def get_status(self) -> ChaosStatus:
        """Get current chaos configuration for this node."""
        resp = await self._ipc.get("/cell/chaos/status")
        resp.raise_for_status()
        return ChaosStatus.from_dict(resp.json())

    async def suspend_gossip(self, suspended: bool = True) -> None:
        """Suspend or resume SWIM gossip heartbeats."""
        resp = await self._ipc.post(
            "/cell/chaos/gossip",
            params={"suspended": str(suspended).lower()}
        )
        resp.raise_for_status()

    async def set_network_fault(self, 
                                node_id: Optional[str] = None, 
                                status_code: Optional[int] = None, 
                                latency_ms: Optional[int] = None) -> None:
        """Inject network faults for specific remote nodes."""
        params = {}
        if node_id: params["nodeId"] = node_id
        if status_code: params["statusCode"] = str(status_code)
        if latency_ms: params["latencyMs"] = str(latency_ms)
        
        resp = await self._ipc.post("/cell/chaos/network", params=params)
        resp.raise_for_status()

    async def set_storage_fault(self, enabled: bool = True) -> None:
        """Enable or disable shared storage mutation faults."""
        resp = await self._ipc.post(
            "/cell/chaos/storage",
            params={"enabled": str(enabled).lower()}
        )
        resp.raise_for_status()
