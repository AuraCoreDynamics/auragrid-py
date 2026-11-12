"""Service Registry client for accessing AuraGrid IServiceRegistry via IPC bridge.

Provides both synchronous (``RegistryClient``) and asynchronous
(``AsyncRegistryClient``) clients for discovering other services
running on the grid.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .ipc import AsyncIpcClient, IpcClient

logger = logging.getLogger("auragrid.registry_client")


@dataclass
class ServiceEndpoint:
    """Represents a discovered service endpoint."""
    service_id: str
    service_name: str
    node_id: str
    endpoint_url: str
    capabilities: List[str]
    metadata: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ServiceEndpoint:
        return cls(
            service_id=data["serviceId"],
            service_name=data["serviceName"],
            node_id=data["nodeId"],
            endpoint_url=data.get("endpointUrl") or data.get("grpcEndpoint") or "",
            capabilities=data.get("capabilities", []),
            metadata=data.get("metadata", {})
        )


class RegistryClient:
    """Synchronous registry client backed by IPC bridge."""

    def __init__(self, ipc_client: IpcClient) -> None:
        self._ipc = ipc_client

    def discover(self, service_name: str) -> List[ServiceEndpoint]:
        """Discover all endpoints for a given service name."""
        resp = self._ipc.get(
            "/cell/registry/discover",
            params={"serviceName": service_name}
        )
        resp.raise_for_status()
        endpoints_data = resp.json().get("endpoints", [])
        return [ServiceEndpoint.from_dict(e) for e in endpoints_data]


class AsyncRegistryClient:
    """Asynchronous registry client backed by IPC bridge."""

    def __init__(self, ipc_client: AsyncIpcClient) -> None:
        self._ipc = ipc_client

    async def discover(self, service_name: str) -> List[ServiceEndpoint]:
        """Discover all endpoints for a given service name."""
        resp = await self._ipc.get(
            "/cell/registry/discover",
            params={"serviceName": service_name}
        )
        resp.raise_for_status()
        endpoints_data = resp.json().get("endpoints", [])
        return [ServiceEndpoint.from_dict(e) for e in endpoints_data]
