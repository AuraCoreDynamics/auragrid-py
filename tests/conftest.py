"""Shared test fixtures for AuraGrid Python SDK tests."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from auragrid.ipc import IpcOptions


@pytest.fixture()
def ipc_options() -> IpcOptions:
    """Return IPC options pointing at a test port with a test token."""
    return IpcOptions(port=19999, token="test-token-abc", timeout=2.0, max_retries=1, backoff_factor=0.0)


def make_json_response(
    data: Any,
    status_code: int = 200,
) -> httpx.Response:
    """Build an ``httpx.Response`` with JSON content for mock transports."""
    content = json.dumps(data).encode("utf-8")
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers={"content-type": "application/json"},
    )


def make_mock_transport(
    handler: Any,
) -> httpx.MockTransport:
    """Create an ``httpx.MockTransport`` from a handler function.

    The handler receives an ``httpx.Request`` and returns an ``httpx.Response``.
    """
    return httpx.MockTransport(handler)
