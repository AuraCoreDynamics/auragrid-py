"""Low-level IPC HTTP client for communicating with the AuraGrid proxy worker.

The proxy worker exposes a local HTTP API on each node that MAS applications
use to access cell services (configuration, membership, governance).  This
module provides both synchronous (``IpcClient``) and asynchronous
(``AsyncIpcClient``) wrappers around ``httpx`` with automatic retry on
transient failures.

Environment variables
---------------------
``AURAGRID_IPC_PORT``
    Port number of the local IPC bridge (default ``5100``).
``AURAGRID_IPC_TOKEN``
    Shared secret for ``X-AuraGrid-IPC-Token`` header authentication.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx


class IpcError(Exception):
    """Raised when the IPC bridge returns a non-success status code."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"IPC error {status_code}: {message}")


@dataclass
class IpcOptions:
    """Configuration for connecting to the local AuraGrid IPC bridge.

    By default, port and token are read from environment variables
    ``AURAGRID_IPC_PORT`` and ``AURAGRID_IPC_TOKEN``.

    Args:
        port: IPC bridge port number.
        token: Authentication token.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retry attempts on transient errors.
        backoff_factor: Multiplier for exponential backoff between retries.
    """

    port: int = field(default_factory=lambda: int(os.environ.get("AURAGRID_IPC_PORT", "5100")))
    token: str = field(default_factory=lambda: os.environ.get("AURAGRID_IPC_TOKEN", ""))
    fencing_token: str | None = field(default_factory=lambda: os.environ.get("AURAGRID_FENCING_TOKEN"))
    timeout: float = 5.0
    max_retries: int = 2
    backoff_factor: float = 0.5

    @property
    def base_url(self) -> str:
        """Build the base URL for IPC requests."""
        return f"http://localhost:{self.port}"


def _build_headers(token: str, fencing_token: str | None = None) -> dict[str, str]:
    """Build common request headers including the IPC authentication token.

    If a fencing token is provided, it is included as ``X-AuraGrid-Fencing-Token``
    for split-brain protection.
    """
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["X-AuraGrid-IPC-Token"] = token
    if fencing_token:
        headers["X-AuraGrid-Fencing-Token"] = fencing_token
    return headers


def _should_retry(status_code: int) -> bool:
    """Return ``True`` if the status code indicates a retryable server error."""
    return status_code >= 500


def _raise_for_error(response: httpx.Response) -> None:
    """Raise ``IpcError`` if the response indicates failure."""
    if response.status_code >= 400:
        try:
            body = response.json()
            message = body.get("message", response.text)
        except Exception:
            message = response.text
        raise IpcError(response.status_code, message)


class IpcClient:
    """Synchronous HTTP client for the AuraGrid IPC bridge.

    Supports use as a context manager::

        with IpcClient(options) as client:
            data = client.get("/cell/config")
    """

    def __init__(self, options: Optional[IpcOptions] = None) -> None:
        self._options = options or IpcOptions()
        self._client = httpx.Client(
            base_url=self._options.base_url,
            headers=_build_headers(self._options.token, self._options.fencing_token),
            timeout=self._options.timeout,
        )

    def __enter__(self) -> IpcClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    # ----- HTTP verbs with retry -----

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a GET request with retry on transient errors."""
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a POST request with retry on transient errors."""
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a PUT request with retry on transient errors."""
        return self._request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a DELETE request with retry on transient errors."""
        return self._request("DELETE", path, **kwargs)

    # ----- internal -----

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Execute an HTTP request with automatic retry on 5xx and transport errors."""
        last_exc: Optional[Exception] = None
        for attempt in range(self._options.max_retries + 1):
            try:
                response = self._client.request(method, path, **kwargs)
                if _should_retry(response.status_code) and attempt < self._options.max_retries:
                    time.sleep(self._options.backoff_factor * (2 ** attempt))
                    continue
                _raise_for_error(response)
                return response
            except IpcError:
                raise
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < self._options.max_retries:
                    time.sleep(self._options.backoff_factor * (2 ** attempt))
                    continue
                raise IpcError(0, f"Transport error: {exc}") from exc
        # Should not reach here, but just in case
        raise IpcError(0, f"Request failed after retries: {last_exc}")


class AsyncIpcClient:
    """Asynchronous HTTP client for the AuraGrid IPC bridge.

    Supports use as an async context manager::

        async with AsyncIpcClient(options) as client:
            data = await client.get("/cell/config")
    """

    def __init__(self, options: Optional[IpcOptions] = None) -> None:
        self._options = options or IpcOptions()
        self._client = httpx.AsyncClient(
            base_url=self._options.base_url,
            headers=_build_headers(self._options.token, self._options.fencing_token),
            timeout=self._options.timeout,
        )

    async def __aenter__(self) -> AsyncIpcClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying async HTTP client."""
        await self._client.aclose()

    # ----- HTTP verbs with retry -----

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a GET request with retry on transient errors."""
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a POST request with retry on transient errors."""
        return await self._request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a PUT request with retry on transient errors."""
        return await self._request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a DELETE request with retry on transient errors."""
        return await self._request("DELETE", path, **kwargs)

    # ----- internal -----

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Execute an async HTTP request with automatic retry on 5xx and transport errors."""
        import asyncio

        last_exc: Optional[Exception] = None
        for attempt in range(self._options.max_retries + 1):
            try:
                response = await self._client.request(method, path, **kwargs)
                if _should_retry(response.status_code) and attempt < self._options.max_retries:
                    await asyncio.sleep(self._options.backoff_factor * (2 ** attempt))
                    continue
                _raise_for_error(response)
                return response
            except IpcError:
                raise
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < self._options.max_retries:
                    await asyncio.sleep(self._options.backoff_factor * (2 ** attempt))
                    continue
                raise IpcError(0, f"Transport error: {exc}") from exc
        # Should not reach here, but just in case
        raise IpcError(0, f"Request failed after retries: {last_exc}")
