"""Tests for EventClient (sync) and AsyncEventClient (async) event clients."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from auragrid.event_client import AsyncEventClient, EventClient
from auragrid.event_models import AuraEventDto, ConsumeResponse, PublishRequest, WalMarkerDto
from auragrid.ipc import AsyncIpcClient, IpcClient, IpcError, IpcOptions

from .conftest import make_json_response


def _make_sync_client(handler, ipc_options: IpcOptions) -> tuple[IpcClient, EventClient]:
    """Build a sync IpcClient with a mock transport and return (ipc_client, event_client)."""
    transport = httpx.MockTransport(handler)
    ipc_client = IpcClient(ipc_options)
    ipc_client._client = httpx.Client(
        base_url=ipc_options.base_url,
        headers={"Accept": "application/json"},
        timeout=ipc_options.timeout,
        transport=transport,
    )
    return ipc_client, EventClient(ipc_client)


def _make_async_client(handler, ipc_options: IpcOptions) -> tuple[AsyncIpcClient, AsyncEventClient]:
    """Build an async IpcClient with a mock transport and return (ipc_client, event_client)."""
    transport = httpx.MockTransport(handler)
    ipc_client = AsyncIpcClient(ipc_options)
    ipc_client._client = httpx.AsyncClient(
        base_url=ipc_options.base_url,
        headers={"Accept": "application/json"},
        timeout=ipc_options.timeout,
        transport=transport,
    )
    return ipc_client, AsyncEventClient(ipc_client)


SAMPLE_PAYLOAD = b"Hello, AuraGrid!"
SAMPLE_PAYLOAD_B64 = base64.b64encode(SAMPLE_PAYLOAD).decode("ascii")


def _sample_event_json(
    seq: int = 1,
    topic: str = "test-topic",
    payload_b64: str = SAMPLE_PAYLOAD_B64,
) -> dict:
    return {
        "eventId": f"evt-{seq}",
        "topicId": topic,
        "sequenceNumber": seq,
        "timestamp": "2025-06-01T12:00:00Z",
        "sourceNodeId": "node-1",
        "eventType": "test-type",
        "payload": payload_b64,
    }


# ─── Model Tests ──────────────────────────────────────────────────────────────


class TestEventModels:
    """Test Pydantic model serialization/deserialization."""

    def test_aura_event_dto_from_json(self) -> None:
        data = _sample_event_json()
        event = AuraEventDto.model_validate(data)
        assert event.event_id == "evt-1"
        assert event.topic_id == "test-topic"
        assert event.sequence_number == 1
        assert event.source_node_id == "node-1"
        assert event.event_type == "test-type"
        assert event.payload == SAMPLE_PAYLOAD_B64

    def test_aura_event_dto_payload_bytes(self) -> None:
        event = AuraEventDto.model_validate(_sample_event_json())
        assert event.payload_bytes == SAMPLE_PAYLOAD

    def test_aura_event_dto_encode_payload(self) -> None:
        encoded = AuraEventDto.encode_payload(SAMPLE_PAYLOAD)
        assert encoded == SAMPLE_PAYLOAD_B64

    def test_publish_request_from_bytes(self) -> None:
        req = PublishRequest.from_bytes(SAMPLE_PAYLOAD, event_type="my-type")
        dumped = req.model_dump(by_alias=True, exclude_none=True)
        assert dumped["payload"] == SAMPLE_PAYLOAD_B64
        assert dumped["eventType"] == "my-type"

    def test_publish_request_from_bytes_no_type(self) -> None:
        req = PublishRequest.from_bytes(SAMPLE_PAYLOAD)
        dumped = req.model_dump(by_alias=True, exclude_none=True)
        assert "eventType" not in dumped
        assert dumped["payload"] == SAMPLE_PAYLOAD_B64

    def test_consume_response_parses_events(self) -> None:
        data = {"events": [_sample_event_json(1), _sample_event_json(2)]}
        resp = ConsumeResponse.model_validate(data)
        assert len(resp.events) == 2
        assert resp.events[0].sequence_number == 1
        assert resp.events[1].sequence_number == 2

    def test_wal_marker_dto(self) -> None:
        data = {"topicId": "t1", "sequenceNumber": 42, "consumerId": "mas-1"}
        marker = WalMarkerDto.model_validate(data)
        assert marker.topic_id == "t1"
        assert marker.sequence_number == 42
        assert marker.consumer_id == "mas-1"

    def test_payload_roundtrip(self) -> None:
        """Verify bytes -> base64 -> bytes roundtrip."""
        original = b"\x00\x01\x02\xff\xfe\xfd" + b"binary data \xc0\xff\xee"
        encoded = AuraEventDto.encode_payload(original)
        event = AuraEventDto.model_validate({
            **_sample_event_json(),
            "payload": encoded,
        })
        assert event.payload_bytes == original


# ─── Sync EventClient Tests ──────────────────────────────────────────────────


class TestEventClientSync:
    """Tests for the synchronous EventClient."""

    def test_publish_sends_correct_request(self, ipc_options: IpcOptions) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content)
            return make_json_response(_sample_event_json())

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)
        result = events.publish("my-topic", SAMPLE_PAYLOAD, event_type="test-type")

        assert captured["method"] == "POST"
        assert "/cell/events/my-topic" in captured["url"]
        assert captured["body"]["payload"] == SAMPLE_PAYLOAD_B64
        assert captured["body"]["eventType"] == "test-type"
        assert result.event_id == "evt-1"
        assert result.payload_bytes == SAMPLE_PAYLOAD
        ipc.close()

    def test_consume_returns_events(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({
                "events": [_sample_event_json(1), _sample_event_json(2)],
            })

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)
        result = events.consume("test-topic", after=0, count=10)

        assert len(result) == 2
        assert result[0].sequence_number == 1
        assert result[1].sequence_number == 2
        ipc.close()

    def test_consume_passes_query_params(self, ipc_options: IpcOptions) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return make_json_response({"events": []})

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)
        events.consume("my-topic", after=42, count=25)

        assert "after=42" in captured["url"]
        assert "count=25" in captured["url"]
        ipc.close()

    def test_list_topics(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"topics": ["t1", "t2", "t3"]})

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)
        topics = events.list_topics()

        assert topics == ["t1", "t2", "t3"]
        ipc.close()

    def test_topic_exists_true(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"exists": True})

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)
        assert events.topic_exists("my-topic") is True
        ipc.close()

    def test_topic_exists_false(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"exists": False})

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)
        assert events.topic_exists("missing") is False
        ipc.close()

    def test_get_marker(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({
                "topicId": "t1",
                "sequenceNumber": 99,
                "consumerId": "mas-1",
            })

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)
        marker = events.get_marker("t1", consumer_id="mas-1")

        assert marker is not None
        assert marker.topic_id == "t1"
        assert marker.sequence_number == 99
        ipc.close()

    def test_get_marker_none(self, ipc_options: IpcOptions) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({
                "topicId": "t1",
                "sequenceNumber": None,
                "consumerId": "mas-1",
            })

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)
        marker = events.get_marker("t1", consumer_id="mas-1")

        assert marker is None
        ipc.close()

    def test_set_marker(self, ipc_options: IpcOptions) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content)
            return make_json_response({"ok": True})

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)
        events.set_marker("t1", 50, consumer_id="mas-1")

        assert captured["method"] == "PUT"
        assert "/cell/events/markers/mas-1/t1" in captured["url"]
        assert captured["body"]["sequenceNumber"] == 50
        ipc.close()

    def test_eventing_501_error(self, ipc_options: IpcOptions) -> None:
        """Verify that 501 from server raises IpcError."""

        def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(
                {"error": "Eventing not available"},
                status_code=501,
            )

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)
        with pytest.raises(IpcError) as exc_info:
            events.list_topics()
        assert exc_info.value.status_code == 501
        ipc.close()


# ─── Async EventClient Tests ─────────────────────────────────────────────────


class TestAsyncEventClient:
    """Tests for the asynchronous AsyncEventClient."""

    @pytest.mark.asyncio
    async def test_publish(self, ipc_options: IpcOptions) -> None:
        captured: dict = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return make_json_response(_sample_event_json())

        ipc_options.max_retries = 0
        ipc, events = _make_async_client(handler, ipc_options)
        result = await events.publish("my-topic", SAMPLE_PAYLOAD, event_type="test-type")

        assert captured["body"]["payload"] == SAMPLE_PAYLOAD_B64
        assert result.event_id == "evt-1"
        assert result.payload_bytes == SAMPLE_PAYLOAD
        await ipc.close()

    @pytest.mark.asyncio
    async def test_consume(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({
                "events": [_sample_event_json(1), _sample_event_json(2)],
            })

        ipc_options.max_retries = 0
        ipc, events = _make_async_client(handler, ipc_options)
        result = await events.consume("test-topic", after=0, count=10)

        assert len(result) == 2
        assert result[0].sequence_number == 1
        await ipc.close()

    @pytest.mark.asyncio
    async def test_list_topics(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"topics": ["a", "b"]})

        ipc_options.max_retries = 0
        ipc, events = _make_async_client(handler, ipc_options)
        topics = await events.list_topics()

        assert topics == ["a", "b"]
        await ipc.close()

    @pytest.mark.asyncio
    async def test_topic_exists(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({"exists": True})

        ipc_options.max_retries = 0
        ipc, events = _make_async_client(handler, ipc_options)
        assert await events.topic_exists("t1") is True
        await ipc.close()

    @pytest.mark.asyncio
    async def test_get_marker(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response({
                "topicId": "t1",
                "sequenceNumber": 10,
                "consumerId": "c1",
            })

        ipc_options.max_retries = 0
        ipc, events = _make_async_client(handler, ipc_options)
        marker = await events.get_marker("t1", consumer_id="c1")

        assert marker is not None
        assert marker.sequence_number == 10
        await ipc.close()

    @pytest.mark.asyncio
    async def test_set_marker(self, ipc_options: IpcOptions) -> None:
        captured: dict = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return make_json_response({"ok": True})

        ipc_options.max_retries = 0
        ipc, events = _make_async_client(handler, ipc_options)
        await events.set_marker("t1", 25, consumer_id="c1")

        assert captured["body"]["sequenceNumber"] == 25
        await ipc.close()

    @pytest.mark.asyncio
    async def test_subscribe_yields_events_and_updates_marker(self, ipc_options: IpcOptions) -> None:
        """Test that subscribe() yields events and updates marker after each batch."""
        consume_count = 0
        marker_updates: list[dict] = []
        stored_marker_seq: int | None = None

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal consume_count, stored_marker_seq
            url = str(request.url)

            # GET marker — return stored marker or None
            if request.method == "GET" and "/markers/" in url:
                return make_json_response({
                    "topicId": "sub-topic",
                    "sequenceNumber": stored_marker_seq,
                    "consumerId": "test-mas",
                })

            # PUT marker — track the update
            if request.method == "PUT" and "/markers/" in url:
                body = json.loads(request.content)
                marker_updates.append(body)
                stored_marker_seq = body["sequenceNumber"]
                return make_json_response({"ok": True})

            # GET consume — return 2 events first, then 1 event, then empty
            if request.method == "GET" and "/cell/events/sub-topic" in url:
                consume_count += 1
                if consume_count == 1:
                    return make_json_response({
                        "events": [
                            _sample_event_json(seq=1, topic="sub-topic"),
                            _sample_event_json(seq=2, topic="sub-topic"),
                        ],
                    })
                if consume_count == 2:
                    return make_json_response({
                        "events": [
                            _sample_event_json(seq=3, topic="sub-topic"),
                        ],
                    })
                return make_json_response({"events": []})

            return make_json_response({"error": "unexpected"}, status_code=404)

        ipc_options.max_retries = 0
        ipc, events = _make_async_client(handler, ipc_options)

        received: list[AuraEventDto] = []
        # Collect events from two batches (3 total), then break
        async for event in events.subscribe("sub-topic", consumer_id="test-mas", interval=0.01):
            received.append(event)
            if len(received) >= 3:
                break

        assert len(received) == 3
        assert received[0].sequence_number == 1
        assert received[1].sequence_number == 2
        assert received[2].sequence_number == 3

        # Marker should have been updated after first batch (seq=2) and second batch (seq=3)
        # The third batch break may prevent the second marker update since set_marker
        # runs after yielding all events in a batch. With 1 event in batch 2,
        # the break happens right after yielding seq=3, before set_marker for batch 2.
        # So only batch 1's marker update (seq=2) is guaranteed.
        assert len(marker_updates) >= 1
        assert marker_updates[0]["sequenceNumber"] == 2
        await ipc.close()

    @pytest.mark.asyncio
    async def test_eventing_501_error(self, ipc_options: IpcOptions) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return make_json_response(
                {"error": "Eventing not available"},
                status_code=501,
            )

        ipc_options.max_retries = 0
        ipc, events = _make_async_client(handler, ipc_options)
        with pytest.raises(IpcError) as exc_info:
            await events.list_topics()
        assert exc_info.value.status_code == 501
        await ipc.close()


# ─── Subscribe Backoff Tests ─────────────────────────────────────────────────


class TestAsyncSubscribeBackoff:
    """Tests for exponential backoff in AsyncEventClient.subscribe()."""

    @pytest.mark.asyncio
    async def test_async_subscribe_exponential_backoff(self, ipc_options: IpcOptions) -> None:
        """Sleep intervals double on empty consume, reset when events arrive."""
        consume_call = 0
        sleep_intervals: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_intervals.append(seconds)

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal consume_call
            url = str(request.url)
            if request.method == "GET" and "/markers/" in url:
                return make_json_response({"topicId": "t1", "sequenceNumber": None, "consumerId": "c1"})
            if request.method == "PUT" and "/markers/" in url:
                return make_json_response({"ok": True})
            if request.method == "GET" and "/cell/events/" in url:
                consume_call += 1
                if consume_call <= 3:
                    return make_json_response({"events": []})
                if consume_call == 4:
                    return make_json_response({"events": [_sample_event_json(seq=1, topic="t1")]})
                return make_json_response({"events": []})
            return make_json_response({"error": "unexpected"}, status_code=404)

        ipc_options.max_retries = 0
        ipc, events = _make_async_client(handler, ipc_options)

        import unittest.mock
        with unittest.mock.patch("auragrid.event_client.asyncio.sleep", side_effect=mock_sleep):
            received = []
            async for event in events.subscribe("t1", consumer_id="c1", interval=1.0, max_backoff=30.0):
                received.append(event)
                if len(received) >= 1:
                    break

        # 3 empty polls -> sleeps of 1.0, 2.0, 4.0
        assert len(sleep_intervals) == 3
        assert sleep_intervals[0] == pytest.approx(1.0)
        assert sleep_intervals[1] == pytest.approx(2.0)
        assert sleep_intervals[2] == pytest.approx(4.0)
        assert received[0].sequence_number == 1
        await ipc.close()

    @pytest.mark.asyncio
    async def test_async_subscribe_max_backoff_cap(self, ipc_options: IpcOptions) -> None:
        """Sleep never exceeds max_backoff."""
        consume_call = 0
        sleep_intervals: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_intervals.append(seconds)

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal consume_call
            url = str(request.url)
            if request.method == "GET" and "/markers/" in url:
                return make_json_response({"topicId": "t1", "sequenceNumber": None, "consumerId": "c1"})
            if request.method == "GET" and "/cell/events/" in url:
                consume_call += 1
                if consume_call <= 10:
                    return make_json_response({"events": []})
                return make_json_response({"events": [_sample_event_json(seq=1, topic="t1")]})
            if request.method == "PUT" and "/markers/" in url:
                return make_json_response({"ok": True})
            return make_json_response({"error": "unexpected"}, status_code=404)

        ipc_options.max_retries = 0
        ipc, events = _make_async_client(handler, ipc_options)

        import unittest.mock
        with unittest.mock.patch("auragrid.event_client.asyncio.sleep", side_effect=mock_sleep):
            async for event in events.subscribe("t1", consumer_id="c1", interval=1.0, max_backoff=8.0):
                break

        # 1.0, 2.0, 4.0, 8.0, 8.0, 8.0, ... (capped at 8.0)
        assert all(s <= 8.0 for s in sleep_intervals)
        assert sleep_intervals[3] == pytest.approx(8.0)
        await ipc.close()

    @pytest.mark.asyncio
    async def test_async_subscribe_marker_committed_per_batch(self, ipc_options: IpcOptions) -> None:
        """set_marker called once per batch, not per event."""
        marker_updates: list[dict] = []
        consume_call = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal consume_call
            url = str(request.url)
            if request.method == "GET" and "/markers/" in url:
                return make_json_response({"topicId": "t1", "sequenceNumber": None, "consumerId": "c1"})
            if request.method == "PUT" and "/markers/" in url:
                marker_updates.append(json.loads(request.content))
                return make_json_response({"ok": True})
            if request.method == "GET" and "/cell/events/" in url:
                consume_call += 1
                if consume_call == 1:
                    return make_json_response({
                        "events": [
                            _sample_event_json(seq=i, topic="t1")
                            for i in range(1, 6)
                        ],
                    })
                # Second batch: 1 event to trigger break after marker commit
                return make_json_response({
                    "events": [_sample_event_json(seq=6, topic="t1")],
                })
            return make_json_response({"error": "unexpected"}, status_code=404)

        ipc_options.max_retries = 0
        ipc, events = _make_async_client(handler, ipc_options)

        count = 0
        async for event in events.subscribe("t1", consumer_id="c1", interval=0.01):
            count += 1
            # Break on first event of batch 2 — batch 1's marker is already committed
            if count >= 6:
                break

        # Batch 1 (5 events) -> 1 marker update at seq=5
        assert len(marker_updates) >= 1
        assert marker_updates[0]["sequenceNumber"] == 5
        await ipc.close()


class TestSyncSubscribeBackoff:
    """Tests for exponential backoff in EventClient.subscribe()."""

    def test_sync_subscribe_exponential_backoff(self, ipc_options: IpcOptions) -> None:
        """Sleep intervals double on empty consume, reset when events arrive."""
        consume_call = 0
        sleep_intervals: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal consume_call
            url = str(request.url)
            if request.method == "GET" and "/markers/" in url:
                return make_json_response({"topicId": "t1", "sequenceNumber": None, "consumerId": "c1"})
            if request.method == "PUT" and "/markers/" in url:
                return make_json_response({"ok": True})
            if request.method == "GET" and "/cell/events/" in url:
                consume_call += 1
                if consume_call <= 3:
                    return make_json_response({"events": []})
                return make_json_response({"events": [_sample_event_json(seq=1, topic="t1")]})
            return make_json_response({"error": "unexpected"}, status_code=404)

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)

        import unittest.mock
        with unittest.mock.patch("auragrid.event_client.time.sleep", side_effect=lambda s: sleep_intervals.append(s)):
            received = []
            for event in events.subscribe("t1", consumer_id="c1", interval=1.0, max_backoff=30.0):
                received.append(event)
                if len(received) >= 1:
                    break

        assert len(sleep_intervals) == 3
        assert sleep_intervals[0] == pytest.approx(1.0)
        assert sleep_intervals[1] == pytest.approx(2.0)
        assert sleep_intervals[2] == pytest.approx(4.0)
        assert received[0].sequence_number == 1
        ipc.close()

    def test_sync_subscribe_yields_events(self, ipc_options: IpcOptions) -> None:
        """Events yielded in correct order."""
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if request.method == "GET" and "/markers/" in url:
                return make_json_response({"topicId": "t1", "sequenceNumber": None, "consumerId": "c1"})
            if request.method == "PUT" and "/markers/" in url:
                return make_json_response({"ok": True})
            if request.method == "GET" and "/cell/events/" in url:
                return make_json_response({
                    "events": [
                        _sample_event_json(seq=1, topic="t1"),
                        _sample_event_json(seq=2, topic="t1"),
                        _sample_event_json(seq=3, topic="t1"),
                    ],
                })
            return make_json_response({"error": "unexpected"}, status_code=404)

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)

        received = []
        for event in events.subscribe("t1", consumer_id="c1", interval=0.01):
            received.append(event)
            if len(received) >= 3:
                break

        assert len(received) == 3
        assert [e.sequence_number for e in received] == [1, 2, 3]
        ipc.close()

    def test_sync_subscribe_marker_committed_per_batch(self, ipc_options: IpcOptions) -> None:
        """set_marker called once per batch, not per event."""
        marker_updates: list[dict] = []
        consume_call = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal consume_call
            url = str(request.url)
            if request.method == "GET" and "/markers/" in url:
                return make_json_response({"topicId": "t1", "sequenceNumber": None, "consumerId": "c1"})
            if request.method == "PUT" and "/markers/" in url:
                marker_updates.append(json.loads(request.content))
                return make_json_response({"ok": True})
            if request.method == "GET" and "/cell/events/" in url:
                consume_call += 1
                if consume_call == 1:
                    return make_json_response({
                        "events": [
                            _sample_event_json(seq=i, topic="t1")
                            for i in range(1, 6)
                        ],
                    })
                return make_json_response({
                    "events": [_sample_event_json(seq=6, topic="t1")],
                })
            return make_json_response({"error": "unexpected"}, status_code=404)

        ipc_options.max_retries = 0
        ipc, events = _make_sync_client(handler, ipc_options)

        count = 0
        for event in events.subscribe("t1", consumer_id="c1", interval=0.01):
            count += 1
            if count >= 6:
                break

        assert len(marker_updates) >= 1
        assert marker_updates[0]["sequenceNumber"] == 5
        ipc.close()
