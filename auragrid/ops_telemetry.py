"""Typed DevSecOps runtime telemetry DTOs and wire helpers for AuraGrid and AuraSprout.

Aligned strictly with ``auragrid-api/schemas/ops-telemetry.schema.json`` so
managed application services and triage evaluators communicate identically over
``/cell/events/{topicId}`` regardless of whether the host is free ``AuraSprout``
or licensed ``AuraGrid``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated, Any, Literal, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    TypeAdapter,
    field_serializer,
    field_validator,
    model_serializer,
)

if TYPE_CHECKING:
    from .event_models import AuraEventDto

OPS_LOG_ERROR_TOPIC = "ops.logs.error"
OPS_CRASH_REPORT_TOPIC = "ops.lifecycle.crash"
OPS_PERF_ANOMALY_TOPIC = "ops.perf.anomaly"
OPS_SECURITY_AUDIT_TOPIC = "ops.audit.security"

OpsRuntimeTier = Literal["aurasprout", "auragrid"]
OpsPerfMetric = Literal["latency_ms", "rss_mb", "cpu_pct", "error_rate"]
OpsTriagePolicy = Literal["SUPERVISED", "BOUNDED_AUTONOMOUS"]


def _parse_iso_datetime(value: Any) -> datetime:
    """Validate an ISO-8601 date-time string or ``datetime`` instance."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 date-time string or datetime instance")
    if "T" not in value and "t" not in value:
        raise ValueError("timestamp must include both date and time components")
    normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include an explicit timezone offset or 'Z'")
    return parsed


def _format_iso_datetime(value: datetime) -> str:
    """Format a ``datetime`` as an RFC-3339 / ISO-8601 string."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    rendered = value.isoformat()
    if rendered.endswith("+00:00"):
        return rendered[:-6] + "Z"
    return rendered


class StackFrameDto(BaseModel):
    """Structured call-site frame inside an error telemetry event."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    file: str = Field(min_length=1, alias="file")
    line: Optional[int] = Field(default=None, strict=True, ge=0, alias="line")
    function: str = Field(min_length=1, alias="function")
    symbol: Optional[str] = Field(default=None, alias="symbol")

    @model_serializer(mode="wrap")
    def _serialize(
        self,
        handler: SerializerFunctionWrapHandler,
        info: SerializationInfo,
    ) -> dict[str, Any]:
        data = handler(self)
        if "line" not in data:
            data["line"] = self.line
        return data


class OpsProvenanceDto(BaseModel):
    """Source identity and build/environment provenance for an ops telemetry event."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    app_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_.-]+$", alias="appId")
    mas_id: str = Field(min_length=1, alias="masId")
    version: str = Field(min_length=1, alias="version")
    commit_sha: Optional[str] = Field(default=None, min_length=1, alias="commitSha")
    mvenv_digest: Optional[str] = Field(default=None, min_length=1, alias="mvenvDigest")
    node_id: str = Field(min_length=1, alias="nodeId")
    runtime_tier: OpsRuntimeTier = Field(alias="runtimeTier")


class _OpsTelemetryBase(BaseModel):
    """Shared base configuration and RFC-3339 timestamp handling for ops telemetry DTOs."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    timestamp: datetime = Field(alias="timestamp")
    provenance: OpsProvenanceDto = Field(alias="provenance")
    fingerprint: str = Field(min_length=1, alias="fingerprint")

    @field_validator("timestamp", mode="before")
    @classmethod
    def _validate_timestamp(cls, value: Any) -> datetime:
        return _parse_iso_datetime(value)

    @field_serializer("timestamp", when_used="always")
    def _serialize_timestamp(self, value: datetime) -> str:
        return _format_iso_datetime(value)


class OpsLogErrorDto(_OpsTelemetryBase):
    """Structured runtime error/critical log telemetry payload (``ops.logs.error``)."""

    topic: Literal["ops.logs.error"] = Field(default=OPS_LOG_ERROR_TOPIC, alias="topic")
    logger: str = Field(min_length=1, alias="logger")
    level: str = Field(min_length=1, alias="level")
    message: str = Field(min_length=1, alias="message")
    exception_type: Optional[str] = Field(default=None, alias="exceptionType")
    stack_trace: Optional[str] = Field(default=None, alias="stackTrace")
    frames: list[StackFrameDto] = Field(default_factory=list, alias="frames")
    log_tail: list[str] = Field(default_factory=list, alias="logTail")


class OpsCrashReportDto(_OpsTelemetryBase):
    """Process crash lifecycle telemetry payload (``ops.lifecycle.crash``)."""

    topic: Literal["ops.lifecycle.crash"] = Field(default=OPS_CRASH_REPORT_TOPIC, alias="topic")
    exit_code: int = Field(strict=True, alias="exitCode")
    signal: Optional[str] = Field(default=None, alias="signal")
    restart_count: int = Field(strict=True, ge=0, alias="restartCount")
    uptime_seconds: float = Field(strict=True, ge=0, alias="uptimeSeconds")
    stderr_tail: list[str] = Field(default_factory=list, alias="stderrTail")


class OpsPerfAnomalyDto(_OpsTelemetryBase):
    """SLO threshold breach telemetry payload (``ops.perf.anomaly``)."""

    topic: Literal["ops.perf.anomaly"] = Field(default=OPS_PERF_ANOMALY_TOPIC, alias="topic")
    metric: OpsPerfMetric = Field(alias="metric")
    observed_value: float = Field(strict=True, ge=0, alias="observedValue")
    slo_threshold: float = Field(strict=True, ge=0, alias="sloThreshold")
    operation: Optional[str] = Field(default=None, min_length=1, alias="operation")

    @model_serializer(mode="wrap")
    def _serialize(
        self,
        handler: SerializerFunctionWrapHandler,
        info: SerializationInfo,
    ) -> dict[str, Any]:
        data = handler(self)
        if "operation" not in data:
            data["operation"] = self.operation
        return data


OpsTelemetryPayload = Union[OpsLogErrorDto, OpsCrashReportDto, OpsPerfAnomalyDto]

_OPS_PAYLOAD_ADAPTER: TypeAdapter[OpsTelemetryPayload] = TypeAdapter(
    Annotated[OpsTelemetryPayload, Field(discriminator="topic")]
)


def compute_ops_fingerprint(topic: str, app_id: str, *parts: str) -> str:
    """Compute a deterministic 16-hex-char SHA-256 incident deduplication fingerprint.

    Args:
        topic: Canonical ops telemetry topic (e.g. ``ops.logs.error``).
        app_id: Application identifier from provenance.
        *parts: Ordered distinguishing attributes (e.g. exception type, top frame, metric).

    Returns:
        Deterministic ``"fp:<16-hex-chars>"`` string.
    """
    material = "\x1f".join((topic, app_id, *(str(part) for part in parts))).encode("utf-8")
    return "fp:" + hashlib.sha256(material).hexdigest()[:16]


def encode_ops_payload(dto: OpsTelemetryPayload) -> bytes:
    """Encode an ``OpsTelemetryPayload`` DTO to compact UTF-8 JSON bytes for WAL transport."""
    dumped = dto.model_dump(by_alias=True, exclude_none=True)
    return json.dumps(dumped, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def decode_ops_event(event: AuraEventDto) -> OpsTelemetryPayload:
    """Decode an ``AuraEventDto`` payload into its discriminated ``OpsTelemetryPayload`` DTO."""
    raw_text = event.payload_bytes.decode("utf-8")
    parsed = json.loads(raw_text)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object in ops telemetry event payload")
    return _OPS_PAYLOAD_ADAPTER.validate_python(parsed)


__all__ = [
    "OPS_LOG_ERROR_TOPIC",
    "OPS_CRASH_REPORT_TOPIC",
    "OPS_PERF_ANOMALY_TOPIC",
    "OPS_SECURITY_AUDIT_TOPIC",
    "OpsRuntimeTier",
    "OpsPerfMetric",
    "OpsTriagePolicy",
    "StackFrameDto",
    "OpsProvenanceDto",
    "OpsLogErrorDto",
    "OpsCrashReportDto",
    "OpsPerfAnomalyDto",
    "OpsTelemetryPayload",
    "compute_ops_fingerprint",
    "encode_ops_payload",
    "decode_ops_event",
]
