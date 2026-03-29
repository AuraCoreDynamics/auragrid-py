"""Pydantic data models for AuraGrid eventing IPC routes.

These DTOs mirror the C# records in ``AuraGrid.Abstractions.Eventing``,
using camelCase JSON aliases for seamless interop with the .NET IPC bridge.

Event payloads are opaque bytes — the SDK transports them as base64 strings
over the JSON IPC wire but exposes ``bytes`` to Python callers.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AuraEventDto(BaseModel):
    """An event envelope returned from the IPC bridge.

    Mirrors C# ``AuraEvent`` from ``AuraGrid.Abstractions.Eventing``.
    The *payload* field is base64-encoded on the wire; use
    :pyattr:`payload_bytes` for the decoded ``bytes`` value.
    """

    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(alias="eventId")
    topic_id: str = Field(alias="topicId")
    sequence_number: int = Field(alias="sequenceNumber")
    timestamp: datetime = Field(alias="timestamp")
    source_node_id: str = Field(alias="sourceNodeId")
    event_type: Optional[str] = Field(default=None, alias="eventType")
    payload: str = Field(alias="payload", description="Base64-encoded opaque payload")

    @property
    def payload_bytes(self) -> bytes:
        """Decode the base64 payload to raw bytes."""
        return base64.b64decode(self.payload)

    @staticmethod
    def encode_payload(data: bytes) -> str:
        """Encode raw bytes to a base64 string for the wire."""
        return base64.b64encode(data).decode("ascii")


class PublishRequest(BaseModel):
    """Request body for ``POST /cell/events/{topicId}``.

    Mirrors the JSON expected by ``CellApiHandler``.
    """

    model_config = ConfigDict(populate_by_name=True)

    payload: str = Field(alias="payload", description="Base64-encoded payload")
    event_type: Optional[str] = Field(default=None, alias="eventType")

    @classmethod
    def from_bytes(cls, data: bytes, event_type: Optional[str] = None) -> PublishRequest:
        """Create a publish request from raw bytes."""
        return cls(
            payload=base64.b64encode(data).decode("ascii"),
            event_type=event_type,
        )


class ConsumeResponse(BaseModel):
    """Response body from ``GET /cell/events/{topicId}?after=…&count=…``."""

    model_config = ConfigDict(populate_by_name=True)

    events: list[AuraEventDto] = Field(alias="events")


class WalMarkerDto(BaseModel):
    """Consumer marker position within a WAL topic.

    Mirrors C# ``WalMarker`` from ``AuraGrid.Abstractions.Eventing``.
    """

    model_config = ConfigDict(populate_by_name=True)

    topic_id: str = Field(alias="topicId")
    sequence_number: int = Field(alias="sequenceNumber")
    consumer_id: Optional[str] = Field(default=None, alias="consumerId")
