"""Event client for publishing, consuming, and managing WAL-backed events.

Provides both synchronous (``EventClient``) and asynchronous
(``AsyncEventClient``) clients that communicate with the IPC bridge
to access the distributed eventing subsystem.

Mirrors C# ``IEventPublisher``, ``IEventConsumer``, ``ITopicManager``,
and ``IMarkerStore`` from ``AuraGrid.Abstractions.Eventing``.
"""

from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator, Optional

from .event_models import AuraEventDto, ConsumeResponse, PublishRequest, WalMarkerDto
from .ipc import AsyncIpcClient, IpcClient


def _default_consumer_id() -> str:
    """Return the default consumer ID from AURAGRID_MAS_ID, or 'default'."""
    return os.environ.get("AURAGRID_MAS_ID", "default")


class EventClient:
    """Synchronous client for WAL-backed event pub/sub.

    Args:
        client: An ``IpcClient`` instance for HTTP communication.
    """

    def __init__(self, client: IpcClient) -> None:
        self._client = client

    # ─── Publishing ───────────────────────────────────────────────────────

    def publish(
        self,
        topic_id: str,
        payload: bytes,
        event_type: Optional[str] = None,
    ) -> AuraEventDto:
        """Publish a single event to a topic.

        Args:
            topic_id: Target topic identifier.
            payload: Opaque binary payload.
            event_type: Optional application-defined type tag.

        Returns:
            The fully populated event with assigned sequence number and timestamp.
        """
        request = PublishRequest.from_bytes(payload, event_type)
        response = self._client.post(
            f"/cell/events/{topic_id}",
            json=request.model_dump(by_alias=True, exclude_none=True),
        )
        return AuraEventDto.model_validate(response.json())

    # ─── Consuming ────────────────────────────────────────────────────────

    def consume(
        self,
        topic_id: str,
        after: int = 0,
        count: int = 100,
    ) -> list[AuraEventDto]:
        """Consume a batch of events from a topic.

        Args:
            topic_id: Topic to read from.
            after: Sequence number to start reading after (0 = beginning).
            count: Maximum number of events to return.

        Returns:
            List of events in sequence order.
        """
        response = self._client.get(
            f"/cell/events/{topic_id}",
            params={"after": after, "count": count},
        )
        result = ConsumeResponse.model_validate(response.json())
        return result.events

    # ─── Topic Management ─────────────────────────────────────────────────

    def list_topics(self) -> list[str]:
        """List all known topics.

        Returns:
            List of topic identifier strings.
        """
        response = self._client.get("/cell/events/topics")
        body = response.json()
        return body.get("topics", [])

    def topic_exists(self, topic_id: str) -> bool:
        """Check whether a topic exists.

        Args:
            topic_id: Topic to check.

        Returns:
            ``True`` if the topic has at least one event, ``False`` otherwise.
        """
        response = self._client.get(f"/cell/events/topics/{topic_id}/exists")
        body = response.json()
        return body.get("exists", False)

    # ─── Marker Management ────────────────────────────────────────────────

    def get_marker(
        self,
        topic_id: str,
        consumer_id: Optional[str] = None,
    ) -> Optional[WalMarkerDto]:
        """Get the committed marker for a consumer/topic pair.

        Args:
            topic_id: Topic identifier.
            consumer_id: Consumer identifier (defaults to ``AURAGRID_MAS_ID``).

        Returns:
            The marker, or ``None`` if no marker has been committed.
        """
        cid = consumer_id or _default_consumer_id()
        response = self._client.get(f"/cell/events/markers/{cid}/{topic_id}")
        body = response.json()
        if body.get("sequenceNumber") is None:
            return None
        return WalMarkerDto.model_validate(body)

    def set_marker(
        self,
        topic_id: str,
        sequence_number: int,
        consumer_id: Optional[str] = None,
    ) -> None:
        """Commit a marker for a consumer/topic pair.

        Args:
            topic_id: Topic identifier.
            sequence_number: Sequence number to commit.
            consumer_id: Consumer identifier (defaults to ``AURAGRID_MAS_ID``).
        """
        cid = consumer_id or _default_consumer_id()
        self._client.put(
            f"/cell/events/markers/{cid}/{topic_id}",
            json={"sequenceNumber": sequence_number},
        )


class AsyncEventClient:
    """Asynchronous client for WAL-backed event pub/sub.

    Args:
        client: An ``AsyncIpcClient`` instance for HTTP communication.
    """

    def __init__(self, client: AsyncIpcClient) -> None:
        self._client = client

    # ─── Publishing ───────────────────────────────────────────────────────

    async def publish(
        self,
        topic_id: str,
        payload: bytes,
        event_type: Optional[str] = None,
    ) -> AuraEventDto:
        """Publish a single event to a topic.

        Args:
            topic_id: Target topic identifier.
            payload: Opaque binary payload.
            event_type: Optional application-defined type tag.

        Returns:
            The fully populated event with assigned sequence number and timestamp.
        """
        request = PublishRequest.from_bytes(payload, event_type)
        response = await self._client.post(
            f"/cell/events/{topic_id}",
            json=request.model_dump(by_alias=True, exclude_none=True),
        )
        return AuraEventDto.model_validate(response.json())

    # ─── Consuming ────────────────────────────────────────────────────────

    async def consume(
        self,
        topic_id: str,
        after: int = 0,
        count: int = 100,
    ) -> list[AuraEventDto]:
        """Consume a batch of events from a topic.

        Args:
            topic_id: Topic to read from.
            after: Sequence number to start reading after (0 = beginning).
            count: Maximum number of events to return.

        Returns:
            List of events in sequence order.
        """
        response = await self._client.get(
            f"/cell/events/{topic_id}",
            params={"after": after, "count": count},
        )
        result = ConsumeResponse.model_validate(response.json())
        return result.events

    # ─── Topic Management ─────────────────────────────────────────────────

    async def list_topics(self) -> list[str]:
        """List all known topics.

        Returns:
            List of topic identifier strings.
        """
        response = await self._client.get("/cell/events/topics")
        body = response.json()
        return body.get("topics", [])

    async def topic_exists(self, topic_id: str) -> bool:
        """Check whether a topic exists.

        Args:
            topic_id: Topic to check.

        Returns:
            ``True`` if the topic has at least one event, ``False`` otherwise.
        """
        response = await self._client.get(f"/cell/events/topics/{topic_id}/exists")
        body = response.json()
        return body.get("exists", False)

    # ─── Marker Management ────────────────────────────────────────────────

    async def get_marker(
        self,
        topic_id: str,
        consumer_id: Optional[str] = None,
    ) -> Optional[WalMarkerDto]:
        """Get the committed marker for a consumer/topic pair.

        Args:
            topic_id: Topic identifier.
            consumer_id: Consumer identifier (defaults to ``AURAGRID_MAS_ID``).

        Returns:
            The marker, or ``None`` if no marker has been committed.
        """
        cid = consumer_id or _default_consumer_id()
        response = await self._client.get(f"/cell/events/markers/{cid}/{topic_id}")
        body = response.json()
        if body.get("sequenceNumber") is None:
            return None
        return WalMarkerDto.model_validate(body)

    async def set_marker(
        self,
        topic_id: str,
        sequence_number: int,
        consumer_id: Optional[str] = None,
    ) -> None:
        """Commit a marker for a consumer/topic pair.

        Args:
            topic_id: Topic identifier.
            sequence_number: Sequence number to commit.
            consumer_id: Consumer identifier (defaults to ``AURAGRID_MAS_ID``).
        """
        cid = consumer_id or _default_consumer_id()
        await self._client.put(
            f"/cell/events/markers/{cid}/{topic_id}",
            json={"sequenceNumber": sequence_number},
        )

    # ─── Streaming ────────────────────────────────────────────────────────

    async def subscribe(
        self,
        topic_id: str,
        consumer_id: Optional[str] = None,
        count: int = 100,
        interval: float = 1.0,
    ) -> AsyncIterator[AuraEventDto]:
        """Subscribe to a topic, yielding events as they arrive.

        Polls ``consume()`` in a loop, yields individual events, and
        automatically updates the consumer marker after each batch.

        Args:
            topic_id: Topic to subscribe to.
            consumer_id: Consumer identifier (defaults to ``AURAGRID_MAS_ID``).
            count: Maximum events per poll batch.
            interval: Polling interval in seconds when no new events are available.

        Yields:
            Individual ``AuraEventDto`` instances as they become available.
        """
        cid = consumer_id or _default_consumer_id()

        # Start from the last committed marker, or from the beginning
        marker = await self.get_marker(topic_id, cid)
        after = marker.sequence_number if marker else 0

        while True:
            events = await self.consume(topic_id, after=after, count=count)

            if not events:
                await asyncio.sleep(interval)
                continue

            for event in events:
                yield event

            # Update marker to the last event in the batch
            last_seq = events[-1].sequence_number
            await self.set_marker(topic_id, last_seq, cid)
            after = last_seq
