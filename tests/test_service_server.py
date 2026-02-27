"""Tests for the embedded service server."""

from __future__ import annotations

import json
import time

import httpx
import pytest

from auragrid.decorators import auragrid_method, auragrid_service
from auragrid.service_server import ServiceServer


@auragrid_service(name="TestCalc")
class CalcService:
    @auragrid_method()
    def add(self, a: int, b: int) -> int:
        return a + b

    @auragrid_method(name="greet")
    def greet_method(self, name: str = "World") -> str:
        return f"Hello, {name}!"

    @auragrid_method()
    async def async_echo(self, message: str) -> str:
        return message

    @auragrid_method()
    def fail(self) -> None:
        raise ValueError("Intentional failure")


IPC_TOKEN = "test-token-12345"


@pytest.fixture()
def server():
    """Start a service server and yield it, stopping on teardown."""
    instance = CalcService()
    srv = ServiceServer(instance, IPC_TOKEN)
    srv.start()
    time.sleep(0.1)  # Give server time to start
    yield srv
    srv.stop()


def _url(server: ServiceServer, method: str) -> str:
    return f"http://127.0.0.1:{server.port}/invoke/{method}"


def _headers() -> dict[str, str]:
    return {"X-AuraGrid-IPC-Token": IPC_TOKEN, "Content-Type": "application/json"}


class TestServiceServer:
    def test_service_name(self, server: ServiceServer) -> None:
        assert server.service_name == "TestCalc"

    def test_method_names(self, server: ServiceServer) -> None:
        names = server.method_names
        assert "add" in names
        assert "greet" in names
        assert "async_echo" in names
        assert "fail" in names

    def test_successful_invocation(self, server: ServiceServer) -> None:
        response = httpx.post(
            _url(server, "add"),
            headers=_headers(),
            content=json.dumps({"a": 3, "b": 5}),
        )
        assert response.status_code == 200
        assert response.json() == 8

    def test_method_with_default_params(self, server: ServiceServer) -> None:
        response = httpx.post(
            _url(server, "greet"),
            headers=_headers(),
            content=b"{}",
        )
        assert response.status_code == 200
        assert response.json() == "Hello, World!"

    def test_method_with_explicit_params(self, server: ServiceServer) -> None:
        response = httpx.post(
            _url(server, "greet"),
            headers=_headers(),
            content=json.dumps({"name": "AuraGrid"}),
        )
        assert response.status_code == 200
        assert response.json() == "Hello, AuraGrid!"

    def test_async_method(self, server: ServiceServer) -> None:
        response = httpx.post(
            _url(server, "async_echo"),
            headers=_headers(),
            content=json.dumps({"message": "async works"}),
        )
        assert response.status_code == 200
        assert response.json() == "async works"

    def test_auth_failure(self, server: ServiceServer) -> None:
        response = httpx.post(
            _url(server, "add"),
            headers={"X-AuraGrid-IPC-Token": "wrong-token"},
            content=b"{}",
        )
        assert response.status_code == 401

    def test_missing_auth(self, server: ServiceServer) -> None:
        response = httpx.post(
            _url(server, "add"),
            content=b"{}",
        )
        assert response.status_code == 401

    def test_missing_method(self, server: ServiceServer) -> None:
        response = httpx.post(
            _url(server, "nonexistent"),
            headers=_headers(),
            content=b"{}",
        )
        assert response.status_code == 404
        assert "not found" in response.json()["error"].lower()

    def test_method_exception(self, server: ServiceServer) -> None:
        response = httpx.post(
            _url(server, "fail"),
            headers=_headers(),
            content=b"{}",
        )
        assert response.status_code == 500
        assert "Intentional failure" in response.json()["error"]

    def test_invalid_json_body(self, server: ServiceServer) -> None:
        response = httpx.post(
            _url(server, "add"),
            headers=_headers(),
            content=b"not json",
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["error"]

    def test_unknown_route(self, server: ServiceServer) -> None:
        response = httpx.post(
            f"http://127.0.0.1:{server.port}/unknown",
            headers=_headers(),
            content=b"{}",
        )
        assert response.status_code == 404

    def test_ephemeral_port(self, server: ServiceServer) -> None:
        assert server.port > 0

    def test_stop_and_restart(self) -> None:
        instance = CalcService()
        srv = ServiceServer(instance, IPC_TOKEN)
        srv.start()
        time.sleep(0.1)
        port = srv.port

        # Verify it works
        response = httpx.post(
            _url(srv, "add"),
            headers=_headers(),
            content=json.dumps({"a": 1, "b": 2}),
        )
        assert response.status_code == 200

        srv.stop()
        # After stop, requests should fail
        with pytest.raises(httpx.ConnectError):
            httpx.post(
                f"http://127.0.0.1:{port}/invoke/add",
                headers=_headers(),
                content=b"{}",
            )
