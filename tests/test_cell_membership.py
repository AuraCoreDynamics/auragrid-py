"""Tests for CellMembership (sync) and AsyncCellMembership (async) clients."""

from __future__ import annotations

import httpx
import pytest

from auragrid.cell_membership import AsyncCellMembership, CellMembership
from auragrid.ipc import AsyncIpcClient, IpcClient, IpcOptions

from .conftest import make_json_response


def _make_sync_client(handler, ipc_options: IpcOptions) -> tuple[IpcClient, CellMembership]:
    """Build a sync IpcClient with a mock transport and return (ipc_client, membership_client)."""
    transport = httpx.MockTransport(handler)
    ipc_client = IpcClient(ipc_options)
    ipc_client._client = httpx.Client(
        base_url=ipc_options.base_url,
        headers={"Accept": "application/json"},
        timeout=ipc_options.timeout,
        transport=transport,
    )
    return ipc_client, CellMembership(ipc_client)


def _make_async_client(handler, ipc_options: IpcOptions) -> tuple[AsyncIpcClient, AsyncCellMembership]:
    """Build an async IpcClient with a mock transport and return (ipc_client, membership_client)."""
    transport = httpx.MockTransport(handler)
    ipc_client = AsyncIpcClient(ipc_options)
    ipc_client._client = httpx.AsyncClient(
        base_url=ipc_options.base_url,
        headers={"Accept": "application/json"},
        timeout=ipc_options.timeout,
        transport=transport,
    )
    return ipc_client, AsyncCellMembership(ipc_client)


_MEMBER_DATA = {
    "nodeId": "node-1",
    "hostName": "host-1.local",
    "state": "Alive",
    "address": "192.168.1.10:5100",
    "lastHeartbeat": "2025-01-15T12:00:00Z",
    "incarnation": 3,
}

_MEMBERS_RESPONSE = {
    "members": [
        _MEMBER_DATA,
        {
            "nodeId": "node-2",
            "state": "Suspected",
            "lastHeartbeat": "2025-01-15T11:30:00Z",
            "incarnation": 1,
        },
    ]
}

_METADATA_RESPONSE = {
    "healthyCount": 5,
    "totalCount": 7,
    "lastUpdated": "2025-01-15T12:00:00Z",
    "incarnationNumber": 42,
    "protocol": "SWIM",
}


class TestCellMembershipSync:
    """Tests for the synchronous CellMembership client."""

    def test_get_members(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_MEMBERS_RESPONSE)

        ipc_options.max_retries = 0
        ipc, membership = _make_sync_client(handler, ipc_options)
        members = membership.get_members()
        assert len(members) == 2
        assert members[0].node_id == "node-1"
        assert members[1].state == "Suspected"
        ipc.close()

    def test_get_members_include_unhealthy(self, ipc_options: IpcOptions) -> None:
        captured_params: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_params.update(dict(request.url.params))
            return make_json_response(_MEMBERS_RESPONSE)

        ipc_options.max_retries = 0
        ipc, membership = _make_sync_client(handler, ipc_options)
        membership.get_members(include_unhealthy=True)
        assert captured_params.get("includeUnhealthy") == "true"
        ipc.close()

    def test_get_member(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_MEMBER_DATA)

        ipc_options.max_retries = 0
        ipc, membership = _make_sync_client(handler, ipc_options)
        member = membership.get_member("node-1")
        assert member is not None
        assert member.node_id == "node-1"
        assert member.host_name == "host-1.local"
        ipc.close()

    def test_get_member_not_found(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({})

        ipc_options.max_retries = 0
        ipc, membership = _make_sync_client(handler, ipc_options)
        member = membership.get_member("nonexistent")
        assert member is None
        ipc.close()

    def test_get_local_node(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_MEMBER_DATA)

        ipc_options.max_retries = 0
        ipc, membership = _make_sync_client(handler, ipc_options)
        local = membership.get_local_node()
        assert local.node_id == "node-1"
        assert membership._local_node_id == "node-1"
        ipc.close()

    def test_local_node_id_property(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_MEMBER_DATA)

        ipc_options.max_retries = 0
        ipc, membership = _make_sync_client(handler, ipc_options)
        # Property should trigger get_local_node() on first access
        node_id = membership.local_node_id
        assert node_id == "node-1"
        ipc.close()

    def test_get_healthy_count(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"count": 5})

        ipc_options.max_retries = 0
        ipc, membership = _make_sync_client(handler, ipc_options)
        count = membership.get_healthy_count()
        assert count == 5
        ipc.close()

    def test_get_metadata(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_METADATA_RESPONSE)

        ipc_options.max_retries = 0
        ipc, membership = _make_sync_client(handler, ipc_options)
        meta = membership.get_metadata()
        assert meta.healthy_count == 5
        assert meta.total_count == 7
        assert meta.protocol == "SWIM"
        assert meta.incarnation_number == 42
        ipc.close()


class TestAsyncCellMembership:
    """Tests for the asynchronous AsyncCellMembership client."""

    @pytest.mark.asyncio
    async def test_get_members(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_MEMBERS_RESPONSE)

        ipc_options.max_retries = 0
        ipc, membership = _make_async_client(handler, ipc_options)
        members = await membership.get_members()
        assert len(members) == 2
        assert members[0].node_id == "node-1"
        await ipc.close()

    @pytest.mark.asyncio
    async def test_get_member(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_MEMBER_DATA)

        ipc_options.max_retries = 0
        ipc, membership = _make_async_client(handler, ipc_options)
        member = await membership.get_member("node-1")
        assert member is not None
        assert member.node_id == "node-1"
        await ipc.close()

    @pytest.mark.asyncio
    async def test_get_local_node(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_MEMBER_DATA)

        ipc_options.max_retries = 0
        ipc, membership = _make_async_client(handler, ipc_options)
        local = await membership.get_local_node()
        assert local.node_id == "node-1"
        assert membership.local_node_id == "node-1"
        await ipc.close()

    @pytest.mark.asyncio
    async def test_local_node_id_none_before_fetch(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_MEMBER_DATA)

        ipc_options.max_retries = 0
        ipc, membership = _make_async_client(handler, ipc_options)
        assert membership.local_node_id is None
        await ipc.close()

    @pytest.mark.asyncio
    async def test_get_healthy_count(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"count": 5})

        ipc_options.max_retries = 0
        ipc, membership = _make_async_client(handler, ipc_options)
        count = await membership.get_healthy_count()
        assert count == 5
        await ipc.close()

    @pytest.mark.asyncio
    async def test_get_metadata(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_METADATA_RESPONSE)

        ipc_options.max_retries = 0
        ipc, membership = _make_async_client(handler, ipc_options)
        meta = await membership.get_metadata()
        assert meta.healthy_count == 5
        assert meta.protocol == "SWIM"
        await ipc.close()
