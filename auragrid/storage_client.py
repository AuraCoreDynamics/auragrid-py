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

    def write(self, path: str, data: bytes, fencing_token: Optional[int] = None) -> None:
        """Write data to a path in grid storage.
        
        Args:
            path: Storage-relative path.
            data: Bytes to write.
            fencing_token: Optional fencing token to validate against lease.
        """
        params = {"path": path}
        if fencing_token is not None:
            params["fencingToken"] = str(fencing_token)
            
        resp = self._ipc.post(
            "/cell/storage/write",
            params=params,
            content=data,
        )
        resp.raise_for_status()

    def append(self, path: str, data: bytes, fencing_token: Optional[int] = None) -> int:
        """Append data to an existing file in grid storage.
        
        Args:
            path: Storage-relative path.
            data: Bytes to append.
            fencing_token: Optional fencing token to validate against lease.
            
        Returns:
            New file length after append.
        """
        params = {"path": path}
        if fencing_token is not None:
            params["fencingToken"] = str(fencing_token)
            
        resp = self._ipc.post(
            "/cell/storage/append",
            params=params,
            content=data,
        )
        resp.raise_for_status()
        return resp.json().get("length", 0)

    def delete(self, path: str, recursive: bool = False) -> bool:
        """Delete a file or directory in grid storage.
        
        Args:
            path: Path to delete.
            recursive: Whether to recursively delete directories.
            
        Returns:
            True if deleted, False if not found.
        """
        resp = self._ipc.delete(
            "/cell/storage/delete",
            params={"path": path, "recursive": str(recursive).lower()},
        )
        resp.raise_for_status()
        return resp.json().get("deleted", False)


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

    async def write(self, path: str, data: bytes, fencing_token: Optional[int] = None) -> None:
        """Write data to a path in grid storage."""
        params = {"path": path}
        if fencing_token is not None:
            params["fencingToken"] = str(fencing_token)

        resp = await self._ipc.post(
            "/cell/storage/write",
            params=params,
            content=data,
        )
        resp.raise_for_status()

    async def append(self, path: str, data: bytes, fencing_token: Optional[int] = None) -> int:
        """Append data to an existing file in grid storage."""
        params = {"path": path}
        if fencing_token is not None:
            params["fencingToken"] = str(fencing_token)

        resp = await self._ipc.post(
            "/cell/storage/append",
            params=params,
            content=data,
        )
        resp.raise_for_status()
        return resp.json().get("length", 0)

    async def delete(self, path: str, recursive: bool = False) -> bool:
        """Delete a file or directory in grid storage."""
        resp = await self._ipc.delete(
            "/cell/storage/delete",
            params={"path": path, "recursive": str(recursive).lower()},
        )
        resp.raise_for_status()
        return resp.json().get("deleted", False)
