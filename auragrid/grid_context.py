"""High-level grid context providing unified access to all cell API clients.

``GridContext`` (sync) and ``AsyncGridContext`` (async) are the primary
entry points for Python MAS applications that need to interact with
cell services (configuration, membership, governance).

When ``@auragrid_service`` decorated classes are provided, the context
automatically starts an embedded service server and registers its port
with the ProxyWorker.

Environment variables
---------------------
``AURAGRID_IPC_PORT``
    Port number of the local IPC bridge (default ``5100``).
``AURAGRID_IPC_TOKEN``
    Shared secret for IPC authentication.
``AURAGRID_MAS_ID``
    The MAS application ID assigned by the grid.
``AURAGRID_NODE_ID``
    The local node ID in the cell.
``AURAGRID_FENCING_TOKEN``
    Fencing token for split-brain protection.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .cell_config import AsyncCellConfiguration, CellConfiguration
from .cell_membership import AsyncCellMembership, CellMembership
from .event_client import AsyncEventClient, EventClient
from .governance import AsyncGovernanceClient, GovernanceClient
from .ipc import AsyncIpcClient, IpcClient, IpcError, IpcOptions
from .service_server import ServiceServer
from .storage_client import AsyncStorageClient, StorageClient

logger = logging.getLogger("auragrid.grid_context")


class GridContext:
    """Synchronous high-level context for accessing AuraGrid cell services.

    Provides lazy-initialized sub-clients for configuration, membership,
    and governance, all sharing a single ``IpcClient`` connection.

    If ``service_instances`` are provided (objects of ``@auragrid_service``
    decorated classes), an embedded service server is started automatically
    and the port is registered with the ProxyWorker.

    Usage::

        with GridContext() as ctx:
            value = ctx.config.get("filesystem/grid-root")
            members = ctx.membership.get_members()
            decision = ctx.governance.can_deploy("my-app", "admin")
    """

    def __init__(
        self,
        options: Optional[IpcOptions] = None,
        service_instances: Optional[list[object]] = None,
    ) -> None:
        self._options = options or IpcOptions()
        self._ipc_client = IpcClient(self._options)
        self._config: Optional[CellConfiguration] = None
        self._membership: Optional[CellMembership] = None
        self._governance: Optional[GovernanceClient] = None
        self._events: Optional[EventClient] = None
        self._storage: Optional[StorageClient] = None
        self._service_servers: list[ServiceServer] = []

        if service_instances:
            self._start_service_servers(service_instances)

    def __enter__(self) -> GridContext:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying IPC client and stop service servers."""
        for server in self._service_servers:
            server.stop()
        self._service_servers.clear()
        self._ipc_client.close()

    # ----- sub-clients (lazy) -----

    @property
    def config(self) -> CellConfiguration:
        """Cell configuration client."""
        if self._config is None:
            self._config = CellConfiguration(self._ipc_client)
        return self._config

    @property
    def membership(self) -> CellMembership:
        """Cell membership client."""
        if self._membership is None:
            self._membership = CellMembership(self._ipc_client)
        return self._membership

    @property
    def governance(self) -> GovernanceClient:
        """Governance policy client."""
        if self._governance is None:
            self._governance = GovernanceClient(self._ipc_client)
        return self._governance

    @property
    def events(self) -> EventClient:
        """Event pub/sub client."""
        if self._events is None:
            self._events = EventClient(self._ipc_client)
        return self._events

    @property
    def storage(self) -> StorageClient:
        """Grid storage client for file I/O including range reads."""
        if self._storage is None:
            self._storage = StorageClient(self._ipc_client)
        return self._storage

    # ----- grid identity -----

    @property
    def mas_id(self) -> Optional[str]:
        """The MAS application ID from ``AURAGRID_MAS_ID`` environment variable."""
        return os.environ.get("AURAGRID_MAS_ID")

    @property
    def node_id(self) -> Optional[str]:
        """The local node ID from ``AURAGRID_NODE_ID`` environment variable."""
        return os.environ.get("AURAGRID_NODE_ID")

    @property
    def fencing_token(self) -> Optional[str]:
        """The fencing token from ``AURAGRID_FENCING_TOKEN`` environment variable."""
        return os.environ.get("AURAGRID_FENCING_TOKEN")

    @property
    def is_connected(self) -> bool:
        """Check if the IPC bridge is reachable by issuing a health check.

        Returns:
            ``True`` if the bridge responds, ``False`` otherwise.
        """
        try:
            self._ipc_client.get("/api/health")
            return True
        except (IpcError, Exception):
            return False

    # ----- service server -----

    def _start_service_servers(self, instances: list[object]) -> None:
        """Start embedded service servers for each service instance."""
        for instance in instances:
            if not hasattr(instance.__class__, "_auragrid_service_meta"):
                continue

            server = ServiceServer(instance, self._options.token)
            server.start()
            self._service_servers.append(server)

            # Report port to ProxyWorker
            try:
                self._ipc_client.post(
                    "/cell/service-port",
                    json={
                        "port": server.port,
                        "serviceName": server.service_name,
                        "ipcToken": self._options.token,
                        "methods": server.method_names,
                    },
                )
                logger.info(
                    "Registered service '%s' on port %d with ProxyWorker",
                    server.service_name,
                    server.port,
                )
            except Exception as e:
                logger.warning(
                    "Failed to register service '%s' port with ProxyWorker: %s",
                    server.service_name,
                    e,
                )


class AsyncGridContext:
    """Asynchronous high-level context for accessing AuraGrid cell services.

    Provides lazy-initialized sub-clients for configuration, membership,
    and governance, all sharing a single ``AsyncIpcClient`` connection.

    If ``service_instances`` are provided (objects of ``@auragrid_service``
    decorated classes), an embedded service server is started automatically
    and the port is registered with the ProxyWorker.

    Usage::

        async with AsyncGridContext() as ctx:
            value = await ctx.config.get("filesystem/grid-root")
            members = await ctx.membership.get_members()
            decision = await ctx.governance.can_deploy("my-app", "admin")
    """

    def __init__(
        self,
        options: Optional[IpcOptions] = None,
        service_instances: Optional[list[object]] = None,
    ) -> None:
        self._options = options or IpcOptions()
        self._ipc_client = AsyncIpcClient(self._options)
        self._config: Optional[AsyncCellConfiguration] = None
        self._membership: Optional[AsyncCellMembership] = None
        self._governance: Optional[AsyncGovernanceClient] = None
        self._events: Optional[AsyncEventClient] = None
        self._storage: Optional[AsyncStorageClient] = None
        self._service_servers: list[ServiceServer] = []
        self._pending_instances = service_instances

    async def __aenter__(self) -> AsyncGridContext:
        if self._pending_instances:
            await self._start_service_servers(self._pending_instances)
            self._pending_instances = None
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying async IPC client and stop service servers."""
        for server in self._service_servers:
            server.stop()
        self._service_servers.clear()
        await self._ipc_client.close()

    # ----- sub-clients (lazy) -----

    @property
    def config(self) -> AsyncCellConfiguration:
        """Cell configuration client (async)."""
        if self._config is None:
            self._config = AsyncCellConfiguration(self._ipc_client)
        return self._config

    @property
    def membership(self) -> AsyncCellMembership:
        """Cell membership client (async)."""
        if self._membership is None:
            self._membership = AsyncCellMembership(self._ipc_client)
        return self._membership

    @property
    def governance(self) -> AsyncGovernanceClient:
        """Governance policy client (async)."""
        if self._governance is None:
            self._governance = AsyncGovernanceClient(self._ipc_client)
        return self._governance

    @property
    def events(self) -> AsyncEventClient:
        """Event pub/sub client (async)."""
        if self._events is None:
            self._events = AsyncEventClient(self._ipc_client)
        return self._events

    @property
    def storage(self) -> AsyncStorageClient:
        """Grid storage client for file I/O including range reads (async)."""
        if self._storage is None:
            self._storage = AsyncStorageClient(self._ipc_client)
        return self._storage

    # ----- grid identity -----

    @property
    def mas_id(self) -> Optional[str]:
        """The MAS application ID from ``AURAGRID_MAS_ID`` environment variable."""
        return os.environ.get("AURAGRID_MAS_ID")

    @property
    def node_id(self) -> Optional[str]:
        """The local node ID from ``AURAGRID_NODE_ID`` environment variable."""
        return os.environ.get("AURAGRID_NODE_ID")

    @property
    def fencing_token(self) -> Optional[str]:
        """The fencing token from ``AURAGRID_FENCING_TOKEN`` environment variable."""
        return os.environ.get("AURAGRID_FENCING_TOKEN")

    @property
    def is_connected(self) -> bool:
        """Check if the IPC bridge connection is available.

        Returns:
            ``True`` if the underlying client is not closed, ``False`` otherwise.
        """
        return not self._ipc_client._client.is_closed

    # ----- service server -----

    async def _start_service_servers(self, instances: list[object]) -> None:
        """Start embedded service servers for each service instance."""
        for instance in instances:
            if not hasattr(instance.__class__, "_auragrid_service_meta"):
                continue

            server = ServiceServer(instance, self._options.token)
            server.start()
            self._service_servers.append(server)

            # Report port to ProxyWorker
            try:
                await self._ipc_client.post(
                    "/cell/service-port",
                    json={
                        "port": server.port,
                        "serviceName": server.service_name,
                        "ipcToken": self._options.token,
                        "methods": server.method_names,
                    },
                )
                logger.info(
                    "Registered service '%s' on port %d with ProxyWorker",
                    server.service_name,
                    server.port,
                )
            except Exception as e:
                logger.warning(
                    "Failed to register service '%s' port with ProxyWorker: %s",
                    server.service_name,
                    e,
                )
