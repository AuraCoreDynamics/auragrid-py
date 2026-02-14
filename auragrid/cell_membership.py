"""Cell membership client for querying node membership and health.

Provides both synchronous (``CellMembership``) and asynchronous
(``AsyncCellMembership``) clients that communicate with the IPC bridge
to access the SWIM-gossip-backed membership list.

Mirrors C# ``ICellMembership`` from
``AuraGrid.Abstractions.Configuration``.
"""

from __future__ import annotations

from typing import Optional

from .ipc import AsyncIpcClient, IpcClient
from .models import CellMember, CellMembershipMetadata, CellMembersResponse


class CellMembership:
    """Synchronous client for cell membership queries.

    Args:
        client: An ``IpcClient`` instance for HTTP communication.
    """

    def __init__(self, client: IpcClient) -> None:
        self._client = client
        self._local_node_id: Optional[str] = None

    @property
    def local_node_id(self) -> str:
        """The local node ID, cached after first retrieval.

        Raises:
            RuntimeError: If the local node ID has not been fetched yet.
                Call ``get_local_node()`` first.
        """
        if self._local_node_id is None:
            node = self.get_local_node()
            self._local_node_id = node.node_id
        return self._local_node_id

    def get_members(self, include_unhealthy: bool = False) -> list[CellMember]:
        """Get all current members of the cell.

        Args:
            include_unhealthy: Include dead/unhealthy members (default ``False``).

        Returns:
            List of cell members.
        """
        response = self._client.get(
            "/cell/members",
            params={"includeUnhealthy": str(include_unhealthy).lower()},
        )
        result = CellMembersResponse.model_validate(response.json())
        return result.members

    def get_member(self, node_id: str) -> Optional[CellMember]:
        """Get information about a specific member by node ID.

        Args:
            node_id: Node identifier.

        Returns:
            Member info, or ``None`` if not found.
        """
        response = self._client.get(f"/cell/members/{node_id}")
        body = response.json()
        if not body:
            return None
        return CellMember.model_validate(body)

    def get_local_node(self) -> CellMember:
        """Get the current local node's information.

        Returns:
            The local node's ``CellMember`` record.
        """
        response = self._client.get("/cell/local-node")
        member = CellMember.model_validate(response.json())
        self._local_node_id = member.node_id
        return member

    def get_healthy_count(self) -> int:
        """Get the count of healthy members in the cell.

        Returns:
            Number of healthy members.
        """
        response = self._client.get("/cell/members/_healthy-count")
        body = response.json()
        return body.get("count", 0)

    def get_metadata(self) -> CellMembershipMetadata:
        """Get metadata about the membership system.

        Returns:
            Membership metadata including counts and protocol info.
        """
        response = self._client.get("/cell/members/_metadata")
        return CellMembershipMetadata.model_validate(response.json())


class AsyncCellMembership:
    """Asynchronous client for cell membership queries.

    Args:
        client: An ``AsyncIpcClient`` instance for HTTP communication.
    """

    def __init__(self, client: AsyncIpcClient) -> None:
        self._client = client
        self._local_node_id: Optional[str] = None

    @property
    def local_node_id(self) -> Optional[str]:
        """The local node ID, available after calling ``get_local_node()``.

        Returns ``None`` if ``get_local_node()`` has not been called yet.
        """
        return self._local_node_id

    async def get_members(self, include_unhealthy: bool = False) -> list[CellMember]:
        """Get all current members of the cell.

        Args:
            include_unhealthy: Include dead/unhealthy members (default ``False``).

        Returns:
            List of cell members.
        """
        response = await self._client.get(
            "/cell/members",
            params={"includeUnhealthy": str(include_unhealthy).lower()},
        )
        result = CellMembersResponse.model_validate(response.json())
        return result.members

    async def get_member(self, node_id: str) -> Optional[CellMember]:
        """Get information about a specific member by node ID.

        Args:
            node_id: Node identifier.

        Returns:
            Member info, or ``None`` if not found.
        """
        response = await self._client.get(f"/cell/members/{node_id}")
        body = response.json()
        if not body:
            return None
        return CellMember.model_validate(body)

    async def get_local_node(self) -> CellMember:
        """Get the current local node's information.

        Returns:
            The local node's ``CellMember`` record.
        """
        response = await self._client.get("/cell/local-node")
        member = CellMember.model_validate(response.json())
        self._local_node_id = member.node_id
        return member

    async def get_healthy_count(self) -> int:
        """Get the count of healthy members in the cell.

        Returns:
            Number of healthy members.
        """
        response = await self._client.get("/cell/members/_healthy-count")
        body = response.json()
        return body.get("count", 0)

    async def get_metadata(self) -> CellMembershipMetadata:
        """Get metadata about the membership system.

        Returns:
            Membership metadata including counts and protocol info.
        """
        response = await self._client.get("/cell/members/_metadata")
        return CellMembershipMetadata.model_validate(response.json())
