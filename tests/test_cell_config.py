"""Tests for CellConfiguration (sync) and AsyncCellConfiguration (async) clients."""

from __future__ import annotations

import json

import httpx
import pytest

from auragrid.cell_config import AsyncCellConfiguration, CellConfiguration
from auragrid.ipc import AsyncIpcClient, IpcClient, IpcOptions

from .conftest import make_json_response


def _make_sync_client(handler, ipc_options: IpcOptions) -> tuple[IpcClient, CellConfiguration]:
    """Build a sync IpcClient with a mock transport and return (ipc_client, config_client)."""
    transport = httpx.MockTransport(handler)
    ipc_client = IpcClient(ipc_options)
    ipc_client._client = httpx.Client(
        base_url=ipc_options.base_url,
        headers={"Accept": "application/json"},
        timeout=ipc_options.timeout,
        transport=transport,
    )
    return ipc_client, CellConfiguration(ipc_client)


def _make_async_client(handler, ipc_options: IpcOptions) -> tuple[AsyncIpcClient, AsyncCellConfiguration]:
    """Build an async IpcClient with a mock transport and return (ipc_client, config_client)."""
    transport = httpx.MockTransport(handler)
    ipc_client = AsyncIpcClient(ipc_options)
    ipc_client._client = httpx.AsyncClient(
        base_url=ipc_options.base_url,
        headers={"Accept": "application/json"},
        timeout=ipc_options.timeout,
        transport=transport,
    )
    return ipc_client, AsyncCellConfiguration(ipc_client)


class TestCellConfigurationSync:
    """Tests for the synchronous CellConfiguration client."""

    def test_get_existing_key(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({
                "value": "/data/grid",
            })

        ipc_options.max_retries = 0
        ipc, config = _make_sync_client(handler, ipc_options)
        value = config.get("filesystem/grid-root")
        assert value == "/data/grid"
        ipc.close()

    def test_get_missing_key(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({
                "value": None,
            })

        ipc_options.max_retries = 0
        ipc, config = _make_sync_client(handler, ipc_options)
        value = config.get("nonexistent")
        assert value is None
        ipc.close()

    def test_get_all(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({
                "config": {"key1": "val1", "key2": 42},
            })

        ipc_options.max_retries = 0
        ipc, config = _make_sync_client(handler, ipc_options)
        all_config = config.get_all()
        assert all_config == {"key1": "val1", "key2": 42}
        ipc.close()

    def test_set(self, ipc_options: IpcOptions) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            captured["method"] = request.method
            return make_json_response({"ok": True})

        ipc_options.max_retries = 0
        ipc, config = _make_sync_client(handler, ipc_options)
        config.set("my-key", "my-value")
        assert captured["method"] == "PUT"
        assert captured["body"] == {"value": "my-value"}
        ipc.close()

    def test_remove_found(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"removed": True})

        ipc_options.max_retries = 0
        ipc, config = _make_sync_client(handler, ipc_options)
        result = config.remove("my-key")
        assert result is True
        ipc.close()

    def test_remove_not_found(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"removed": False})

        ipc_options.max_retries = 0
        ipc, config = _make_sync_client(handler, ipc_options)
        result = config.remove("missing-key")
        assert result is False
        ipc.close()

    def test_get_metadata(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({
                "keyCount": 5,
                "maxVersion": 10,
                "lastModified": "2025-01-15T12:00:00Z",
                "lastModifiedByNodeId": "node-1",
                "synchronizedNodeCount": 3,
                "storagePath": "/grid/config.json",
            })

        ipc_options.max_retries = 0
        ipc, config = _make_sync_client(handler, ipc_options)
        meta = config.get_metadata()
        assert meta.key_count == 5
        assert meta.max_version == 10
        assert meta.last_modified_by_node_id == "node-1"
        ipc.close()


class TestAsyncCellConfiguration:
    """Tests for the asynchronous AsyncCellConfiguration client."""

    @pytest.mark.asyncio
    async def test_get_existing_key(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({
                "value": "/data/grid",
            })

        ipc_options.max_retries = 0
        ipc, config = _make_async_client(handler, ipc_options)
        value = await config.get("filesystem/grid-root")
        assert value == "/data/grid"
        await ipc.close()

    @pytest.mark.asyncio
    async def test_get_missing_key(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({
                "value": None,
            })

        ipc_options.max_retries = 0
        ipc, config = _make_async_client(handler, ipc_options)
        value = await config.get("nonexistent")
        assert value is None
        await ipc.close()

    @pytest.mark.asyncio
    async def test_get_all(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"config": {"a": 1, "b": "two"}})

        ipc_options.max_retries = 0
        ipc, config = _make_async_client(handler, ipc_options)
        result = await config.get_all()
        assert result == {"a": 1, "b": "two"}
        await ipc.close()

    @pytest.mark.asyncio
    async def test_set(self, ipc_options: IpcOptions) -> None:
        captured: dict = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return make_json_response({"ok": True})

        ipc_options.max_retries = 0
        ipc, config = _make_async_client(handler, ipc_options)
        await config.set("key1", "value1")
        assert captured["body"] == {"value": "value1"}
        await ipc.close()

    @pytest.mark.asyncio
    async def test_remove(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"removed": True})

        ipc_options.max_retries = 0
        ipc, config = _make_async_client(handler, ipc_options)
        result = await config.remove("key1")
        assert result is True
        await ipc.close()

    @pytest.mark.asyncio
    async def test_get_metadata(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({
                "keyCount": 8,
                "maxVersion": 20,
                "lastModified": "2025-01-15T12:00:00Z",
                "synchronizedNodeCount": 5,
            })

        ipc_options.max_retries = 0
        ipc, config = _make_async_client(handler, ipc_options)
        meta = await config.get_metadata()
        assert meta.key_count == 8
        assert meta.synchronized_node_count == 5
        await ipc.close()

    @pytest.mark.asyncio
    async def test_watch_yields_on_change(self, ipc_options: IpcOptions) -> None:
        call_count = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return make_json_response({"value": "v1"})
            return make_json_response({"value": "v2"})

        ipc_options.max_retries = 0
        ipc, config = _make_async_client(handler, ipc_options)

        values = []
        count = 0
        async for value in config.watch("k", interval=0.01):
            values.append(value)
            count += 1
            if count >= 2:
                break

        assert values[0] == "v1"
        assert values[1] == "v2"
        await ipc.close()
