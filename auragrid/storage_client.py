"""Storage client for accessing AuraGrid IStorageProvider via IPC bridge.

Provides both synchronous (``StorageClient``) and asynchronous
(``AsyncStorageClient``) clients for reading data from the grid's
shared storage, including range-read support for geospatial windowed access.
"""

from __future__ import annotations

import logging
from typing import Optional

from .ipc import AsyncIpcClient, IpcClient, IpcOptions

logger = logging.getLogger("auragrid.storage_client")


class StorageClient:
    """Synchronous storage client backed by IPC bridge.

    Usage::

        client = StorageClient(ipc_client)
        data = client.read_range("imagery/scene.tif", offset=0, count=4096)
    """

    def __init__(self, ipc_client: IpcClient) -> None:
        self._ipc = ipc_client

    def read_range(self, path: str, offset: int, count: int) -> Optional[bytes]:
        """Read a range of bytes from a file in grid storage.

        Args:
            path: Storage-relative path (forward slashes).
            offset: Byte offset to start reading from.
            count: Maximum number of bytes to read.

        Returns:
            Bytes read, or None if the file does not exist.
        """
        resp = self._ipc.get(
            "/cell/storage/range",
            params={"path": path, "offset": str(offset), "count": str(count)},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content

    def read(self, path: str) -> Optional[bytes]:
        """Read entire file contents from grid storage.

        Args:
            path: Storage-relative path.

        Returns:
            File contents, or None if not found.
        """
        resp = self._ipc.get(
            "/cell/storage/read",
            params={"path": path},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content

    def exists(self, path: str) -> bool:
        """Check if a path exists in grid storage."""
        resp = self._ipc.get(
            "/cell/storage/exists",
            params={"path": path},
        )
        resp.raise_for_status()
        return resp.json().get("exists", False)

    def get_metadata(self, path: str) -> Optional[dict]:
        """Get file metadata without downloading contents."""
        resp = self._ipc.get(
            "/cell/storage/metadata",
            params={"path": path},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


class AsyncStorageClient:
    """Asynchronous storage client backed by IPC bridge.

    Usage::

        async with AsyncStorageClient(async_ipc_client) as client:
            data = await client.read_range("imagery/scene.tif", 0, 4096)
    """

    def __init__(self, ipc_client: AsyncIpcClient) -> None:
        self._ipc = ipc_client

    async def read_range(self, path: str, offset: int, count: int) -> Optional[bytes]:
        """Read a range of bytes from a file in grid storage."""
        resp = await self._ipc.get(
            "/cell/storage/range",
            params={"path": path, "offset": str(offset), "count": str(count)},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content

    async def read(self, path: str) -> Optional[bytes]:
        """Read entire file contents from grid storage."""
        resp = await self._ipc.get(
            "/cell/storage/read",
            params={"path": path},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content

    async def exists(self, path: str) -> bool:
        """Check if a path exists in grid storage."""
        resp = await self._ipc.get(
            "/cell/storage/exists",
            params={"path": path},
        )
        resp.raise_for_status()
        return resp.json().get("exists", False)

    async def get_metadata(self, path: str) -> Optional[dict]:
        """Get file metadata without downloading contents."""
        resp = await self._ipc.get(
            "/cell/storage/metadata",
            params={"path": path},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
