"""Tests for GovernanceClient (sync) and AsyncGovernanceClient (async)."""

from __future__ import annotations

import json

import httpx
import pytest

from auragrid.governance import AsyncGovernanceClient, GovernanceClient
from auragrid.ipc import AsyncIpcClient, IpcClient, IpcOptions

from .conftest import make_json_response


def _make_sync_client(handler, ipc_options: IpcOptions) -> tuple[IpcClient, GovernanceClient]:
    """Build a sync IpcClient with a mock transport and return (ipc_client, governance_client)."""
    transport = httpx.MockTransport(handler)
    ipc_client = IpcClient(ipc_options)
    ipc_client._client = httpx.Client(
        base_url=ipc_options.base_url,
        headers={"Accept": "application/json"},
        timeout=ipc_options.timeout,
        transport=transport,
    )
    return ipc_client, GovernanceClient(ipc_client)


def _make_async_client(handler, ipc_options: IpcOptions) -> tuple[AsyncIpcClient, AsyncGovernanceClient]:
    """Build an async IpcClient with a mock transport and return (ipc_client, governance_client)."""
    transport = httpx.MockTransport(handler)
    ipc_client = AsyncIpcClient(ipc_options)
    ipc_client._client = httpx.AsyncClient(
        base_url=ipc_options.base_url,
        headers={"Accept": "application/json"},
        timeout=ipc_options.timeout,
        transport=transport,
    )
    return ipc_client, AsyncGovernanceClient(ipc_client)


_DECISION_PERMIT = {"isPermitted": True}
_DECISION_DENY = {"isPermitted": False, "denyReason": "Insufficient role"}
_ROLES_RESPONSE = {"userId": "admin", "roles": ["admin", "deployer"]}
_AUDIT_RESPONSE = {
    "entries": [
        {
            "action": "Deploy",
            "appId": "my-app",
            "userId": "admin",
            "permitted": True,
            "timestamp": "2025-01-15T12:00:00Z",
            "source": "cli",
            "entryHash": "abc123",
        },
        {
            "action": "Remove",
            "appId": "old-app",
            "userId": "viewer",
            "permitted": False,
            "denyReason": "Not authorized",
            "timestamp": "2025-01-14T10:00:00Z",
        },
    ]
}


class TestGovernanceClientSync:
    """Tests for the synchronous GovernanceClient."""

    def test_can_deploy_permitted(self, ipc_options: IpcOptions) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            captured["path"] = str(request.url.path)
            return make_json_response(_DECISION_PERMIT)

        ipc_options.max_retries = 0
        ipc, gov = _make_sync_client(handler, ipc_options)
        decision = gov.can_deploy("my-app", "admin")
        assert decision.is_permitted is True
        assert captured["body"] == {"appId": "my-app", "userId": "admin"}
        assert "/can-deploy" in captured["path"]
        ipc.close()

    def test_can_deploy_denied(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_DECISION_DENY)

        ipc_options.max_retries = 0
        ipc, gov = _make_sync_client(handler, ipc_options)
        decision = gov.can_deploy("my-app", "viewer")
        assert decision.is_permitted is False
        assert decision.deny_reason == "Insufficient role"
        ipc.close()

    def test_can_remove(self, ipc_options: IpcOptions) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = str(request.url.path)
            return make_json_response(_DECISION_PERMIT)

        ipc_options.max_retries = 0
        ipc, gov = _make_sync_client(handler, ipc_options)
        decision = gov.can_remove("old-app", "admin")
        assert decision.is_permitted is True
        assert "/can-remove" in captured["path"]
        ipc.close()

    def test_can_reconfigure(self, ipc_options: IpcOptions) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = str(request.url.path)
            return make_json_response(_DECISION_PERMIT)

        ipc_options.max_retries = 0
        ipc, gov = _make_sync_client(handler, ipc_options)
        decision = gov.can_reconfigure("my-app", "admin")
        assert decision.is_permitted is True
        assert "/can-reconfigure" in captured["path"]
        ipc.close()

    def test_get_user_roles(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_ROLES_RESPONSE)

        ipc_options.max_retries = 0
        ipc, gov = _make_sync_client(handler, ipc_options)
        roles = gov.get_user_roles("admin")
        assert roles == ["admin", "deployer"]
        ipc.close()

    def test_get_audit_trail(self, ipc_options: IpcOptions) -> None:
        captured_params: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_params.update(dict(request.url.params))
            return make_json_response(_AUDIT_RESPONSE)

        ipc_options.max_retries = 0
        ipc, gov = _make_sync_client(handler, ipc_options)
        entries = gov.get_audit_trail(limit=50)
        assert len(entries) == 2
        assert entries[0].action == "Deploy"
        assert entries[0].app_id == "my-app"
        assert entries[0].entry_hash == "abc123"
        assert entries[1].permitted is False
        assert entries[1].deny_reason == "Not authorized"
        assert captured_params.get("limit") == "50"
        ipc.close()

    def test_get_audit_trail_list_format(self, ipc_options: IpcOptions) -> None:
        """Test audit trail when the API returns a plain list (not wrapped in dict)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response([
                {
                    "action": "Deploy",
                    "appId": "app-1",
                    "userId": "user-1",
                    "permitted": True,
                    "timestamp": "2025-01-15T12:00:00Z",
                },
            ])

        ipc_options.max_retries = 0
        ipc, gov = _make_sync_client(handler, ipc_options)
        entries = gov.get_audit_trail()
        assert len(entries) == 1
        assert entries[0].app_id == "app-1"
        ipc.close()


class TestAsyncGovernanceClient:
    """Tests for the asynchronous AsyncGovernanceClient."""

    @pytest.mark.asyncio
    async def test_can_deploy_permitted(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_DECISION_PERMIT)

        ipc_options.max_retries = 0
        ipc, gov = _make_async_client(handler, ipc_options)
        decision = await gov.can_deploy("my-app", "admin")
        assert decision.is_permitted is True
        await ipc.close()

    @pytest.mark.asyncio
    async def test_can_deploy_denied(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_DECISION_DENY)

        ipc_options.max_retries = 0
        ipc, gov = _make_async_client(handler, ipc_options)
        decision = await gov.can_deploy("my-app", "viewer")
        assert decision.is_permitted is False
        assert decision.deny_reason == "Insufficient role"
        await ipc.close()

    @pytest.mark.asyncio
    async def test_can_remove(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_DECISION_PERMIT)

        ipc_options.max_retries = 0
        ipc, gov = _make_async_client(handler, ipc_options)
        decision = await gov.can_remove("old-app", "admin")
        assert decision.is_permitted is True
        await ipc.close()

    @pytest.mark.asyncio
    async def test_can_reconfigure(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_DECISION_PERMIT)

        ipc_options.max_retries = 0
        ipc, gov = _make_async_client(handler, ipc_options)
        decision = await gov.can_reconfigure("my-app", "admin")
        assert decision.is_permitted is True
        await ipc.close()

    @pytest.mark.asyncio
    async def test_get_user_roles(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_ROLES_RESPONSE)

        ipc_options.max_retries = 0
        ipc, gov = _make_async_client(handler, ipc_options)
        roles = await gov.get_user_roles("admin")
        assert roles == ["admin", "deployer"]
        await ipc.close()

    @pytest.mark.asyncio
    async def test_get_audit_trail(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(_AUDIT_RESPONSE)

        ipc_options.max_retries = 0
        ipc, gov = _make_async_client(handler, ipc_options)
        entries = await gov.get_audit_trail(limit=25)
        assert len(entries) == 2
        assert entries[0].action == "Deploy"
        assert entries[1].permitted is False
        await ipc.close()
