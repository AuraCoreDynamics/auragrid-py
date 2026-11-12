"""Wire contract alignment tests verifying auragrid-py Pydantic DTOs against auragrid-api."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from auragrid import (
    AuraEventDto,
    AuditEntry,
    CellConfigMetadata,
    CellMember,
    ConflictResolutionAction,
    GovernanceDecision,
    LeaseConflictDto,
    LeaseRecordDto,
    MasPlacementMode,
    WalMarkerDto,
    WorkBatchClaimDto,
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
