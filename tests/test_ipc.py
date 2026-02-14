"""Tests for the IPC client (sync and async), including retry, error handling, and headers."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from auragrid.ipc import AsyncIpcClient, IpcClient, IpcError, IpcOptions

from .conftest import make_json_response, make_mock_transport


class TestIpcOptions:
    """Tests for IpcOptions defaults and base_url."""

    def test_defaults(self) -> None:
        opts = IpcOptions(port=5100, token="")
        assert opts.port == 5100
        assert opts.timeout == 5.0
        assert opts.max_retries == 2
        assert opts.backoff_factor == 0.5

    def test_base_url(self) -> None:
        opts = IpcOptions(port=8080, token="tok")
        assert opts.base_url == "http://localhost:8080"


class TestIpcError:
    """Tests for the IpcError exception."""

    def test_attributes(self) -> None:
        err = IpcError(404, "Not found")
        assert err.status_code == 404
        assert err.message == "Not found"
        assert "404" in str(err)
        assert "Not found" in str(err)


class TestIpcClientSync:
    """Tests for the synchronous IpcClient."""

    def test_get_success(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"ok": True})

        transport = make_mock_transport(handler)
        ipc_options.max_retries = 0
        client = IpcClient(ipc_options)
        client._client = httpx.Client(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json", "X-AuraGrid-IPC-Token": ipc_options.token},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        response = client.get("/api/test")
        assert response.json() == {"ok": True}
        client.close()

    def test_post_sends_json(self, ipc_options: IpcOptions) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            captured["method"] = request.method
            return make_json_response({"saved": True})

        transport = make_mock_transport(handler)
        ipc_options.max_retries = 0
        client = IpcClient(ipc_options)
        client._client = httpx.Client(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json", "X-AuraGrid-IPC-Token": ipc_options.token},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        client.post("/api/test", json={"key": "val"})
        assert captured["method"] == "POST"
        assert captured["body"] == {"key": "val"}
        client.close()

    def test_ipc_token_header(self, ipc_options: IpcOptions) -> None:
        captured_headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return make_json_response({"ok": True})

        transport = make_mock_transport(handler)
        ipc_options.max_retries = 0
        client = IpcClient(ipc_options)
        client._client = httpx.Client(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json", "X-AuraGrid-IPC-Token": "my-secret"},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        client.get("/api/test")
        assert captured_headers.get("x-auragrid-ipc-token") == "my-secret"
        client.close()

    def test_4xx_raises_ipc_error(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"message": "Not found"}, status_code=404)

        transport = make_mock_transport(handler)
        ipc_options.max_retries = 0
        client = IpcClient(ipc_options)
        client._client = httpx.Client(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json"},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        with pytest.raises(IpcError) as exc_info:
            client.get("/api/missing")
        assert exc_info.value.status_code == 404
        client.close()

    def test_5xx_retries_then_raises(self, ipc_options: IpcOptions) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return make_json_response({"message": "Server error"}, status_code=503)

        transport = make_mock_transport(handler)
        ipc_options.max_retries = 2
        ipc_options.backoff_factor = 0.0
        client = IpcClient(ipc_options)
        client._client = httpx.Client(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json"},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        with pytest.raises(IpcError) as exc_info:
            client.get("/api/failing")
        assert exc_info.value.status_code == 503
        assert call_count == 3  # 1 initial + 2 retries
        client.close()

    def test_5xx_retries_then_succeeds(self, ipc_options: IpcOptions) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return make_json_response({"message": "Server error"}, status_code=500)
            return make_json_response({"ok": True})

        transport = make_mock_transport(handler)
        ipc_options.max_retries = 2
        ipc_options.backoff_factor = 0.0
        client = IpcClient(ipc_options)
        client._client = httpx.Client(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json"},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        response = client.get("/api/flaky")
        assert response.json() == {"ok": True}
        assert call_count == 3
        client.close()

    def test_context_manager(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"ok": True})

        transport = make_mock_transport(handler)
        ipc_options.max_retries = 0
        with IpcClient(ipc_options) as client:
            client._client = httpx.Client(
                base_url=ipc_options.base_url,
                headers={"Accept": "application/json"},
                timeout=ipc_options.timeout,
                transport=transport,
            )
            response = client.get("/api/test")
            assert response.json() == {"ok": True}

    def test_delete_method(self, ipc_options: IpcOptions) -> None:
        captured_method: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_method.append(request.method)
            return make_json_response({"removed": True})

        transport = make_mock_transport(handler)
        ipc_options.max_retries = 0
        client = IpcClient(ipc_options)
        client._client = httpx.Client(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json"},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        client.delete("/api/test")
        assert captured_method[0] == "DELETE"
        client.close()

    def test_put_method(self, ipc_options: IpcOptions) -> None:
        captured_method: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_method.append(request.method)
            return make_json_response({"updated": True})

        transport = make_mock_transport(handler)
        ipc_options.max_retries = 0
        client = IpcClient(ipc_options)
        client._client = httpx.Client(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json"},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        client.put("/api/test", json={"key": "value"})
        assert captured_method[0] == "PUT"
        client.close()


class TestAsyncIpcClient:
    """Tests for the asynchronous AsyncIpcClient."""

    @pytest.mark.asyncio
    async def test_get_success(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"ok": True})

        transport = httpx.MockTransport(handler)
        ipc_options.max_retries = 0
        client = AsyncIpcClient(ipc_options)
        client._client = httpx.AsyncClient(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json", "X-AuraGrid-IPC-Token": ipc_options.token},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        response = await client.get("/api/test")
        assert response.json() == {"ok": True}
        await client.close()

    @pytest.mark.asyncio
    async def test_4xx_raises_ipc_error(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"message": "Forbidden"}, status_code=403)

        transport = httpx.MockTransport(handler)
        ipc_options.max_retries = 0
        client = AsyncIpcClient(ipc_options)
        client._client = httpx.AsyncClient(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json"},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        with pytest.raises(IpcError) as exc_info:
            await client.get("/api/forbidden")
        assert exc_info.value.status_code == 403
        await client.close()

    @pytest.mark.asyncio
    async def test_5xx_retries(self, ipc_options: IpcOptions) -> None:
        call_count = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return make_json_response({"message": "error"}, status_code=502)
            return make_json_response({"ok": True})

        transport = httpx.MockTransport(handler)
        ipc_options.max_retries = 2
        ipc_options.backoff_factor = 0.0
        client = AsyncIpcClient(ipc_options)
        client._client = httpx.AsyncClient(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json"},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        response = await client.get("/api/flaky")
        assert response.json() == {"ok": True}
        assert call_count == 3
        await client.close()

    @pytest.mark.asyncio
    async def test_async_context_manager(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"ok": True})

        transport = httpx.MockTransport(handler)
        ipc_options.max_retries = 0
        async with AsyncIpcClient(ipc_options) as client:
            client._client = httpx.AsyncClient(
                base_url=ipc_options.base_url,
                headers={"Accept": "application/json"},
                timeout=ipc_options.timeout,
                transport=transport,
            )
            response = await client.get("/api/test")
            assert response.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_post_async(self, ipc_options: IpcOptions) -> None:
        captured: dict[str, Any] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return make_json_response({"created": True}, status_code=200)

        transport = httpx.MockTransport(handler)
        ipc_options.max_retries = 0
        client = AsyncIpcClient(ipc_options)
        client._client = httpx.AsyncClient(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json"},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        await client.post("/api/test", json={"data": 123})
        assert captured["body"] == {"data": 123}
        await client.close()

    @pytest.mark.asyncio
    async def test_ipc_token_header_async(self, ipc_options: IpcOptions) -> None:
        captured_headers: dict[str, str] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return make_json_response({"ok": True})

        transport = httpx.MockTransport(handler)
        ipc_options.max_retries = 0
        client = AsyncIpcClient(ipc_options)
        client._client = httpx.AsyncClient(
            base_url=ipc_options.base_url,
            headers={"Accept": "application/json", "X-AuraGrid-IPC-Token": "async-secret"},
            timeout=ipc_options.timeout,
            transport=transport,
        )
        await client.get("/api/test")
        assert captured_headers.get("x-auragrid-ipc-token") == "async-secret"
        await client.close()
