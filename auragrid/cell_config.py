"""Cell configuration client for reading and writing cell-level configuration.

Provides both synchronous (``CellConfiguration``) and asynchronous
(``AsyncCellConfiguration``) clients that communicate with the IPC bridge
to access the distributed cell configuration backed by gossip-based
synchronization.

Mirrors C# ``ICellConfiguration`` from
``AuraGrid.Abstractions.Configuration``.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Optional

from .ipc import AsyncIpcClient, IpcClient
from .models import CellConfigAllResponse, CellConfigMetadata, CellConfigValueResponse


class CellConfiguration:
    """Synchronous client for cell configuration management.

    Args:
        client: An ``IpcClient`` instance for HTTP communication.
    """

    def __init__(self, client: IpcClient) -> None:
        self._client = client

    def get(self, key: str) -> Any:
        """Get a single configuration value by key.

        Args:
            key: Configuration key (e.g., ``"filesystem/wal-path"``).

        Returns:
            The configuration value, or ``None`` if the key does not exist.
        """
        response = self._client.get(f"/cell/config/{key}")
        result = CellConfigValueResponse.model_validate(response.json())
        return result.value

    def get_all(self) -> dict[str, Any]:
        """Get all current configuration as a dictionary.

        Returns:
            Complete configuration dictionary.
        """
        response = self._client.get("/cell/config")
        result = CellConfigAllResponse.model_validate(response.json())
        return result.config

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value.

        The change is published via gossip and persisted to shared storage.

        Args:
            key: Configuration key.
            value: Configuration value (must be JSON serializable).
        """
        self._client.put(
            f"/cell/config/{key}",
            json={"value": value},
        )

    def remove(self, key: str) -> bool:
        """Remove a configuration key.

        Args:
            key: Configuration key.

        Returns:
            ``True`` if the key was removed, ``False`` if not found.
        """
        response = self._client.delete(
            f"/cell/config/{key}",
        )
        body = response.json()
        return body.get("removed", False)

    def get_metadata(self) -> CellConfigMetadata:
        """Get metadata about the configuration system.

        Returns:
            Configuration metadata including key count and version info.
        """
        response = self._client.get("/cell/config/_metadata")
        return CellConfigMetadata.model_validate(response.json())


class AsyncCellConfiguration:
    """Asynchronous client for cell configuration management.

    Args:
        client: An ``AsyncIpcClient`` instance for HTTP communication.
    """

    def __init__(self, client: AsyncIpcClient) -> None:
        self._client = client

    async def get(self, key: str) -> Any:
        """Get a single configuration value by key.

        Args:
            key: Configuration key (e.g., ``"filesystem/wal-path"``).

        Returns:
            The configuration value, or ``None`` if the key does not exist.
        """
        response = await self._client.get(f"/cell/config/{key}")
        result = CellConfigValueResponse.model_validate(response.json())
        return result.value

    async def get_all(self) -> dict[str, Any]:
        """Get all current configuration as a dictionary.

        Returns:
            Complete configuration dictionary.
        """
        response = await self._client.get("/cell/config")
        result = CellConfigAllResponse.model_validate(response.json())
        return result.config

    async def set(self, key: str, value: Any) -> None:
        """Set a configuration value.

        The change is published via gossip and persisted to shared storage.

        Args:
            key: Configuration key.
            value: Configuration value (must be JSON serializable).
        """
        await self._client.put(
            f"/cell/config/{key}",
            json={"value": value},
        )

    async def remove(self, key: str) -> bool:
        """Remove a configuration key.

        Args:
            key: Configuration key.

        Returns:
            ``True`` if the key was removed, ``False`` if not found.
        """
        response = await self._client.delete(
            f"/cell/config/{key}",
        )
        body = response.json()
        return body.get("removed", False)

    async def get_metadata(self) -> CellConfigMetadata:
        """Get metadata about the configuration system.

        Returns:
            Configuration metadata including key count and version info.
        """
        response = await self._client.get("/cell/config/_metadata")
        return CellConfigMetadata.model_validate(response.json())

    async def watch(
        self,
        key: str,
        interval: float = 2.0,
    ) -> AsyncIterator[Optional[Any]]:
        """Watch a configuration key for changes, yielding new values.

        Polls the IPC bridge at the specified interval and yields the value
        whenever it changes.

        Args:
            key: Configuration key to watch.
            interval: Polling interval in seconds (default ``2.0``).

        Yields:
            The new value each time the watched key changes.
        """
        previous: Any = object()  # sentinel
        while True:
            current = await self.get(key)
            if current != previous:
                previous = current
                yield current
            await asyncio.sleep(interval)
