"""Tests for GridContext (sync) and AsyncGridContext (async) entry points."""

from __future__ import annotations

import os

import httpx
import pytest

from auragrid.cell_config import AsyncCellConfiguration, CellConfiguration
from auragrid.cell_membership import AsyncCellMembership, CellMembership
from auragrid.governance import AsyncGovernanceClient, GovernanceClient
from auragrid.grid_context import AsyncGridContext, GridContext
from auragrid.ipc import IpcOptions

from .conftest import make_json_response


class TestGridContextSync:
    """Tests for the synchronous GridContext."""

    def test_sub_clients_are_lazy(self) -> None:
        ctx = GridContext(IpcOptions(port=19999, token="tok"))
        assert ctx._config is None
        assert ctx._membership is None
        assert ctx._governance is None
        _ = ctx.config
        _ = ctx.membership
        _ = ctx.governance
        assert ctx._config is not None
        assert ctx._membership is not None
        assert ctx._governance is not None
        ctx.close()

    def test_sub_client_types(self) -> None:
        ctx = GridContext(IpcOptions(port=19999, token="tok"))
        assert isinstance(ctx.config, CellConfiguration)
        assert isinstance(ctx.membership, CellMembership)
        assert isinstance(ctx.governance, GovernanceClient)
        ctx.close()

    def test_context_manager(self) -> None:
        with GridContext(IpcOptions(port=19999, token="tok")) as ctx:
            assert isinstance(ctx.config, CellConfiguration)

    def test_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AURAGRID_MAS_ID", "my-mas")
        monkeypatch.setenv("AURAGRID_NODE_ID", "node-42")
        monkeypatch.setenv("AURAGRID_FENCING_TOKEN", "fence-abc")

        ctx = GridContext(IpcOptions(port=19999, token="tok"))
        assert ctx.mas_id == "my-mas"
        assert ctx.node_id == "node-42"
        assert ctx.fencing_token == "fence-abc"
        ctx.close()

    def test_env_vars_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AURAGRID_MAS_ID", raising=False)
        monkeypatch.delenv("AURAGRID_NODE_ID", raising=False)
        monkeypatch.delenv("AURAGRID_FENCING_TOKEN", raising=False)

        ctx = GridContext(IpcOptions(port=19999, token="tok"))
        assert ctx.mas_id is None
        assert ctx.node_id is None
        assert ctx.fencing_token is None
        ctx.close()

    def test_is_connected_true(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"status": "healthy"})

        transport = httpx.MockTransport(handler)
        opts = IpcOptions(port=19999, token="tok", max_retries=0)
        ctx = GridContext(opts)
        ctx._ipc_client._client = httpx.Client(
            base_url=opts.base_url,
            headers={"Accept": "application/json"},
            timeout=opts.timeout,
            transport=transport,
        )
        assert ctx.is_connected is True
        ctx.close()

    def test_is_connected_false(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(handler)
        opts = IpcOptions(port=19999, token="tok", max_retries=0, backoff_factor=0.0)
        ctx = GridContext(opts)
        ctx._ipc_client._client = httpx.Client(
            base_url=opts.base_url,
            headers={"Accept": "application/json"},
            timeout=opts.timeout,
            transport=transport,
        )
        assert ctx.is_connected is False
        ctx.close()


class TestAsyncGridContext:
    """Tests for the asynchronous AsyncGridContext."""

    def test_sub_clients_are_lazy(self) -> None:
        ctx = AsyncGridContext(IpcOptions(port=19999, token="tok"))
        assert ctx._config is None
        assert ctx._membership is None
        assert ctx._governance is None
        _ = ctx.config
        _ = ctx.membership
        _ = ctx.governance
        assert ctx._config is not None
        assert ctx._membership is not None
        assert ctx._governance is not None

    def test_sub_client_types(self) -> None:
        ctx = AsyncGridContext(IpcOptions(port=19999, token="tok"))
        assert isinstance(ctx.config, AsyncCellConfiguration)
        assert isinstance(ctx.membership, AsyncCellMembership)
        assert isinstance(ctx.governance, AsyncGovernanceClient)

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        async with AsyncGridContext(IpcOptions(port=19999, token="tok")) as ctx:
            assert isinstance(ctx.config, AsyncCellConfiguration)

    def test_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AURAGRID_MAS_ID", "async-mas")
        monkeypatch.setenv("AURAGRID_NODE_ID", "async-node")
        monkeypatch.setenv("AURAGRID_FENCING_TOKEN", "async-fence")

        ctx = AsyncGridContext(IpcOptions(port=19999, token="tok"))
        assert ctx.mas_id == "async-mas"
        assert ctx.node_id == "async-node"
        assert ctx.fencing_token == "async-fence"

    @pytest.mark.asyncio
    async def test_is_connected_true(self) -> None:
        opts = IpcOptions(port=19999, token="tok", max_retries=0)
        ctx = AsyncGridContext(opts)
        assert ctx.is_connected is True
        await ctx.close()

    @pytest.mark.asyncio
    async def test_is_connected_false(self) -> None:
        opts = IpcOptions(port=19999, token="tok", max_retries=0, backoff_factor=0.0)
        ctx = AsyncGridContext(opts)
        await ctx.close()
        assert ctx.is_connected is False
