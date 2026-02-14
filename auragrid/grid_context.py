"""High-level grid context providing unified access to all cell API clients.

``GridContext`` (sync) and ``AsyncGridContext`` (async) are the primary
entry points for Python MAS applications that need to interact with
cell services (configuration, membership, governance).

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

import os
from typing import Any, Optional

from .cell_config import AsyncCellConfiguration, CellConfiguration
from .cell_membership import AsyncCellMembership, CellMembership
from .governance import AsyncGovernanceClient, GovernanceClient
from .ipc import AsyncIpcClient, IpcClient, IpcError, IpcOptions


class GridContext:
    """Synchronous high-level context for accessing AuraGrid cell services.

    Provides lazy-initialized sub-clients for configuration, membership,
    and governance, all sharing a single ``IpcClient`` connection.

    Usage::

        with GridContext() as ctx:
            value = ctx.config.get("filesystem/grid-root")
            members = ctx.membership.get_members()
            decision = ctx.governance.can_deploy("my-app", "admin")
    """

    def __init__(self, options: Optional[IpcOptions] = None) -> None:
        self._options = options or IpcOptions()
        self._ipc_client = IpcClient(self._options)
        self._config: Optional[CellConfiguration] = None
        self._membership: Optional[CellMembership] = None
        self._governance: Optional[GovernanceClient] = None

    def __enter__(self) -> GridContext:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying IPC client."""
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


class AsyncGridContext:
    """Asynchronous high-level context for accessing AuraGrid cell services.

    Provides lazy-initialized sub-clients for configuration, membership,
    and governance, all sharing a single ``AsyncIpcClient`` connection.

    Usage::

        async with AsyncGridContext() as ctx:
            value = await ctx.config.get("filesystem/grid-root")
            members = await ctx.membership.get_members()
            decision = await ctx.governance.can_deploy("my-app", "admin")
    """

    def __init__(self, options: Optional[IpcOptions] = None) -> None:
        self._options = options or IpcOptions()
        self._ipc_client = AsyncIpcClient(self._options)
        self._config: Optional[AsyncCellConfiguration] = None
        self._membership: Optional[AsyncCellMembership] = None
        self._governance: Optional[AsyncGovernanceClient] = None

    async def __aenter__(self) -> AsyncGridContext:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying async IPC client."""
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
