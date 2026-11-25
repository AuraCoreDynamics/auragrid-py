"""Wire contract alignment tests verifying auragrid-py Pydantic DTOs against auragrid-api."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from jsonschema import Draft7Validator, FormatChecker
from pydantic import ValidationError

import auragrid.event_models as event_models_mod
from auragrid import (
    OPS_CRASH_REPORT_TOPIC,
    OPS_LOG_ERROR_TOPIC,
    OPS_PERF_ANOMALY_TOPIC,
    OPS_SECURITY_AUDIT_TOPIC,
    AuraEventDto,
    AuditEntry,
    CellConfigMetadata,
    CellMember,
    ConflictResolutionAction,
    GovernanceDecision,
    LeaseConflictDto,
    LeaseRecordDto,
    MasPlacementMode,
    OpsCrashReportDto,
    OpsLogErrorDto,
    OpsPerfAnomalyDto,
    OpsProvenanceDto,
    StackFrameDto,
    WalMarkerDto,
    WorkBatchClaimDto,
    compute_ops_fingerprint,
    decode_ops_event,
    encode_ops_payload,
)
from auragrid_api import get_schema_path, load_schema, load_wire_vector


def _validate_definition(schema_doc: dict[str, Any], def_name: str, instance: Any) -> None:
    subschema = {
        "$schema": schema_doc.get("$schema", "http://json-schema.org/draft-07/schema#"),
        "definitions": schema_doc.get("definitions", {}),
        "$ref": f"#/definitions/{def_name}",
    }
    jsonschema.validate(instance=instance, schema=subschema)


def _validate_openapi_component(openapi_doc: dict[str, Any], schema_name: str, instance: Any) -> None:
    subschema = {
        "components": {"schemas": openapi_doc["components"]["schemas"]},
        "$ref": f"#/components/schemas/{schema_name}",
    }
    jsonschema.validate(instance=instance, schema=subschema)


def test_pydantic_models_roundtrip_golden_vectors() -> None:
    """Verify field/JSON round-trip fidelity of auragrid DTOs against auragrid-api golden vectors."""
    lease_vectors = load_wire_vector("lease_collaboration_vectors.json")
    ipc_vectors = load_wire_vector("ipc_bridge_vectors.json")
    lease_schema = load_schema("lease-collaboration.schema.json")
    openapi_path = Path(get_schema_path("lease-collaboration.schema.json")).parent.parent / "openapi" / "ipc-bridge.openapi.json"
    ipc_openapi = json.loads(openapi_path.read_text(encoding="utf-8"))

    # 1. Lease & collaboration DTOs against JSON Schema
    lease_record = LeaseRecordDto.model_validate(lease_vectors["leaseRecordDto"])
    lease_dumped = lease_record.model_dump(mode="json", by_alias=True, exclude_none=True)
    _validate_definition(lease_schema, "leaseRecordDto", lease_dumped)
    assert lease_dumped["masId"] == lease_vectors["leaseRecordDto"]["masId"]
    assert lease_dumped["mode"] == MasPlacementMode.CELL_SINGLETON.value
    assert lease_dumped["fencingToken"] == lease_vectors["leaseRecordDto"]["fencingToken"]

    batch_claim = WorkBatchClaimDto.model_validate(lease_vectors["workBatchClaimDto"])
    batch_dumped = batch_claim.model_dump(mode="json", by_alias=True, exclude_none=True)
    _validate_definition(lease_schema, "workBatchClaimDto", batch_dumped)
    assert batch_dumped["batchId"] == lease_vectors["workBatchClaimDto"]["batchId"]
    assert batch_dumped["itemIds"] == lease_vectors["workBatchClaimDto"]["itemIds"]

    conflict = LeaseConflictDto.model_validate(lease_vectors["leaseConflictDto"])
    conflict_dumped = conflict.model_dump(mode="json", by_alias=True, exclude_none=True)
    _validate_definition(lease_schema, "leaseConflictDto", conflict_dumped)
    assert conflict_dumped["conflictId"] == lease_vectors["leaseConflictDto"]["conflictId"]
    assert ConflictResolutionAction.KEEP_LOCAL_AND_STAGE_MERGE in conflict.available_resolutions

    marker = WalMarkerDto.model_validate(lease_vectors["walMarker"])
    marker_dumped = marker.model_dump(mode="json", by_alias=True, exclude_none=True)
    _validate_definition(lease_schema, "walMarker", marker_dumped)
    assert marker_dumped["sequenceNumber"] == lease_vectors["walMarker"]["sequenceNumber"]

    # 2. Core cell IPC DTOs against OpenAPI component schemas
    member = CellMember.model_validate(ipc_vectors["CellMember"])
    member_dumped = member.model_dump(mode="json", by_alias=True, exclude_none=True)
    _validate_openapi_component(ipc_openapi, "CellMember", member_dumped)

    cfg_meta = CellConfigMetadata.model_validate(ipc_vectors["CellConfigMetadata"])
    cfg_dumped = cfg_meta.model_dump(mode="json", by_alias=True, exclude_none=True)
    _validate_openapi_component(ipc_openapi, "CellConfigMetadata", cfg_dumped)

    gov = GovernanceDecision.model_validate(ipc_vectors["GovernanceDecision"])
    gov_dumped = gov.model_dump(mode="json", by_alias=True, exclude_none=True)
    _validate_openapi_component(ipc_openapi, "GovernanceDecision", gov_dumped)

    evt = AuraEventDto.model_validate(ipc_vectors["AuraEventDto"])
    evt_dumped = evt.model_dump(mode="json", by_alias=True, exclude_none=True)
    _validate_openapi_component(ipc_openapi, "AuraEventDto", evt_dumped)

    audit = AuditEntry.model_validate(
        {
            "timestamp": "2026-11-12T10:00:00Z",
            "appId": "model-coordinator",
            "userId": "alice",
            "action": "VolunteerJoin",
            "permitted": True,
        }
    )
    assert audit.model_dump(mode="json", by_alias=True)["userId"] == "alice"


def test_mas_placement_mode_enum_matches_schema() -> None:
    """Ensure Python MasPlacementMode values match app.manifest.schema.json identically."""
    app_schema = load_schema("app.manifest.schema.json")
    schema_modes = app_schema["definitions"]["masMode"]["enum"]
    py_modes = [m.value for m in MasPlacementMode]
    assert py_modes == schema_modes


def test_ops_telemetry_dtos_roundtrip_golden_vectors_and_schema() -> None:
    """Validate all ops_telemetry_vectors.json cases against Pydantic DTOs and ops-telemetry.schema.json."""
    ops_schema = load_schema("ops-telemetry.schema.json")
    ops_vectors = load_wire_vector("ops_telemetry_vectors.json")
    root_validator = Draft7Validator(ops_schema, format_checker=FormatChecker())

    # Topic constants & re-export alignment
    assert [
        OPS_LOG_ERROR_TOPIC,
        OPS_CRASH_REPORT_TOPIC,
        OPS_PERF_ANOMALY_TOPIC,
        OPS_SECURITY_AUDIT_TOPIC,
    ] == ops_schema["definitions"]["opsTopic"]["enum"]
    assert event_models_mod.OpsLogErrorDto is OpsLogErrorDto
    assert event_models_mod.OpsCrashReportDto is OpsCrashReportDto
    assert event_models_mod.OpsPerfAnomalyDto is OpsPerfAnomalyDto
    assert event_models_mod.encode_ops_payload is encode_ops_payload
    assert event_models_mod.decode_ops_event is decode_ops_event

    dto_map: list[tuple[str, type[OpsLogErrorDto | OpsCrashReportDto | OpsPerfAnomalyDto]]] = [
        ("opsLogError", OpsLogErrorDto),
        ("opsCrashReport", OpsCrashReportDto),
        ("opsPerfAnomaly", OpsPerfAnomalyDto),
    ]

    for def_name, dto_cls in dto_map:
        for idx, vector in enumerate(ops_vectors["valid"][def_name]):
            dto = dto_cls.model_validate(vector)
            dumped = dto.model_dump(by_alias=True, exclude_none=True)

            # Must validate cleanly against root schema, opsTelemetryPayload, and specific definition
            root_validator.validate(dumped)
            _validate_definition(ops_schema, def_name, dumped)
            _validate_definition(ops_schema, "opsTelemetryPayload", dumped)

            # Wire helpers round-trip cleanly into compact UTF-8 JSON bytes and back via AuraEventDto
            encoded_bytes = encode_ops_payload(dto)
            assert isinstance(encoded_bytes, bytes)
            wire_obj = json.loads(encoded_bytes.decode("utf-8"))
            root_validator.validate(wire_obj)

            envelope = AuraEventDto(
                event_id=f"evt-{def_name}-{idx}",
                topic_id=dto.topic,
                sequence_number=idx + 1,
                timestamp="2026-11-24T19:05:00Z",
                source_node_id=dto.provenance.node_id,
                event_type=dto.topic,
                payload=AuraEventDto.encode_payload(encoded_bytes),
            )
            decoded = decode_ops_event(envelope)
            assert isinstance(decoded, dto_cls)
            assert decoded == dto

        for bad_vector in ops_vectors["invalid"][def_name]:
            with pytest.raises(ValidationError):
                dto_cls.model_validate(bad_vector)

            bad_envelope = AuraEventDto(
                event_id="evt-bad",
                topic_id=bad_vector.get("topic", OPS_LOG_ERROR_TOPIC),
                sequence_number=1,
                timestamp="2026-11-24T19:05:00Z",
                source_node_id="node-bad",
                payload=AuraEventDto.encode_payload(json.dumps(bad_vector).encode("utf-8")),
            )
            with pytest.raises(ValidationError):
                decode_ops_event(bad_envelope)


def test_ops_telemetry_snake_case_extra_forbid_and_fingerprint() -> None:
    """Verify snake_case construction, nullable line preservation, extra='forbid', and fingerprinting."""
    ops_schema = load_schema("ops-telemetry.schema.json")
    root_validator = Draft7Validator(ops_schema, format_checker=FormatChecker())

    fp1 = compute_ops_fingerprint(OPS_LOG_ERROR_TOPIC, "aurarouter", "ValueError", "router.py:44")
    fp2 = compute_ops_fingerprint(OPS_LOG_ERROR_TOPIC, "aurarouter", "ValueError", "router.py:44")
    fp3 = compute_ops_fingerprint(OPS_LOG_ERROR_TOPIC, "aurarouter", "KeyError", "router.py:44")
    assert fp1 == fp2
    assert fp1 != fp3
    assert fp1.startswith("fp:")
    assert len(fp1) == 19

    prov = OpsProvenanceDto(
        app_id="aurarouter",
        mas_id="coordinator",
        version="4.3.0",
        node_id="sprout-local",
        runtime_tier="aurasprout",
    )
    frame_null_line = StackFrameDto(file="<frozen importlib>", line=None, function="_load")
    err_dto = OpsLogErrorDto(
        timestamp="2026-11-24T19:10:00Z",
        provenance=prov,
        logger="aurarouter.boot",
        level="ERROR",
        message="Import failed",
        frames=[frame_null_line],
        log_tail=["ERROR Import failed"],
        fingerprint=fp1,
    )
    dumped = err_dto.model_dump(by_alias=True, exclude_none=True)
    assert dumped["frames"][0]["line"] is None
    assert "symbol" not in dumped["frames"][0]
    root_validator.validate(dumped)

    with pytest.raises(ValidationError):
        OpsProvenanceDto(
            app_id="aurarouter",
            mas_id="coordinator",
            version="4.3.0",
            node_id="sprout-local",
            runtime_tier="aurasprout",
            unexpected_field="nope",  # type: ignore[call-arg]
        )

