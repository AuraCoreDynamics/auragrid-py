"""Tests for Pydantic model validation, camelCase aliasing, and round-trip serialization."""

from __future__ import annotations

from datetime import datetime, timezone

from auragrid.models import (
    AuditEntry,
    CellConfigAllResponse,
    CellConfigMetadata,
    CellConfigValueResponse,
    CellMember,
    CellMembershipMetadata,
    CellMembersResponse,
    GovernanceDecision,
    IpcErrorResponse,
    UserRolesResponse,
)


class TestCellMember:
    """Tests for the CellMember model."""

    def test_from_camel_case(self) -> None:
        data = {
            "nodeId": "node-1",
            "hostName": "host-1.local",
            "state": "Alive",
            "address": "192.168.1.10:5100",
            "joinedAt": "2025-01-15T10:00:00Z",
            "lastHeartbeat": "2025-01-15T12:00:00Z",
            "registeredServices": ["svc-a", "svc-b"],
            "metadata": {"gpu.vendor": "nvidia"},
            "incarnation": 3,
        }
        member = CellMember.model_validate(data)
        assert member.node_id == "node-1"
        assert member.host_name == "host-1.local"
        assert member.state == "Alive"
        assert member.registered_services == ["svc-a", "svc-b"]
        assert member.incarnation == 3

    def test_from_snake_case(self) -> None:
        data = {
            "node_id": "node-2",
            "state": "Dead",
            "last_heartbeat": "2025-01-15T12:00:00Z",
        }
        member = CellMember.model_validate(data)
        assert member.node_id == "node-2"
        assert member.state == "Dead"

    def test_round_trip(self) -> None:
        data = {
            "nodeId": "node-1",
            "state": "Alive",
            "lastHeartbeat": "2025-01-15T12:00:00Z",
            "incarnation": 5,
        }
        member = CellMember.model_validate(data)
        dumped = member.model_dump(by_alias=True)
        assert dumped["nodeId"] == "node-1"
        assert dumped["state"] == "Alive"
        assert dumped["incarnation"] == 5

    def test_optional_fields_default_none(self) -> None:
        data = {
            "nodeId": "node-1",
            "state": "Alive",
            "lastHeartbeat": "2025-01-15T12:00:00Z",
        }
        member = CellMember.model_validate(data)
        assert member.host_name is None
        assert member.address is None
        assert member.joined_at is None
        assert member.registered_services is None
        assert member.metadata is None


class TestCellMembershipMetadata:
    """Tests for the CellMembershipMetadata model."""

    def test_from_camel_case(self) -> None:
        data = {
            "healthyCount": 5,
            "totalCount": 7,
            "lastUpdated": "2025-01-15T12:00:00Z",
            "incarnationNumber": 42,
            "protocol": "SWIM",
        }
        meta = CellMembershipMetadata.model_validate(data)
        assert meta.healthy_count == 5
        assert meta.total_count == 7
        assert meta.protocol == "SWIM"
        assert meta.incarnation_number == 42

    def test_round_trip(self) -> None:
        data = {
            "healthyCount": 3,
            "totalCount": 3,
            "lastUpdated": "2025-01-15T12:00:00Z",
            "incarnationNumber": 1,
        }
        meta = CellMembershipMetadata.model_validate(data)
        dumped = meta.model_dump(by_alias=True)
        assert dumped["healthyCount"] == 3
        assert dumped["totalCount"] == 3
        assert dumped["incarnationNumber"] == 1


class TestCellMembersResponse:
    """Tests for the CellMembersResponse wrapper."""

    def test_members_list(self) -> None:
        data = {
            "members": [
                {"nodeId": "n1", "state": "Alive", "lastHeartbeat": "2025-01-15T12:00:00Z"},
                {"nodeId": "n2", "state": "Dead", "lastHeartbeat": "2025-01-15T11:00:00Z"},
            ]
        }
        resp = CellMembersResponse.model_validate(data)
        assert len(resp.members) == 2
        assert resp.members[0].node_id == "n1"
        assert resp.members[1].state == "Dead"


class TestCellConfigMetadata:
    """Tests for the CellConfigMetadata model."""

    def test_from_camel_case(self) -> None:
        data = {
            "keyCount": 10,
            "maxVersion": 99,
            "lastModified": "2025-01-15T12:00:00Z",
            "lastModifiedByNodeId": "node-1",
            "synchronizedNodeCount": 3,
            "storagePath": "/grid/config.json",
        }
        meta = CellConfigMetadata.model_validate(data)
        assert meta.key_count == 10
        assert meta.max_version == 99
        assert meta.last_modified_by_node_id == "node-1"
        assert meta.storage_path == "/grid/config.json"


class TestCellConfigValueResponse:
    """Tests for the CellConfigValueResponse model."""

    def test_existing_value(self) -> None:
        data = {"value": "/data/grid"}
        resp = CellConfigValueResponse.model_validate(data)
        assert resp.value == "/data/grid"

    def test_none_value(self) -> None:
        data = {"value": None}
        resp = CellConfigValueResponse.model_validate(data)
        assert resp.value is None


class TestCellConfigAllResponse:
    """Tests for the CellConfigAllResponse model."""

    def test_config_dict(self) -> None:
        data = {"config": {"key1": "val1", "key2": 42}}
        resp = CellConfigAllResponse.model_validate(data)
        assert resp.config == {"key1": "val1", "key2": 42}


class TestGovernanceDecision:
    """Tests for the GovernanceDecision model."""

    def test_permitted(self) -> None:
        data = {"isPermitted": True}
        dec = GovernanceDecision.model_validate(data)
        assert dec.is_permitted is True
        assert dec.deny_reason is None
        assert dec.requires_approval is False

    def test_denied(self) -> None:
        data = {"isPermitted": False, "denyReason": "Insufficient role"}
        dec = GovernanceDecision.model_validate(data)
        assert dec.is_permitted is False
        assert dec.deny_reason == "Insufficient role"

    def test_requires_approval(self) -> None:
        data = {
            "isPermitted": True,
            "requiresApproval": True,
            "denyReason": "Needs manager sign-off",
        }
        dec = GovernanceDecision.model_validate(data)
        assert dec.requires_approval is True

    def test_round_trip(self) -> None:
        data = {
            "isPermitted": False,
            "denyReason": "blocked",
            "requiresApproval": False,
            "metadata": {"policy": "strict"},
        }
        dec = GovernanceDecision.model_validate(data)
        dumped = dec.model_dump(by_alias=True)
        assert dumped["isPermitted"] is False
        assert dumped["denyReason"] == "blocked"
        assert dumped["metadata"] == {"policy": "strict"}


class TestAuditEntry:
    """Tests for the AuditEntry model."""

    def test_from_camel_case(self) -> None:
        data = {
            "action": "Deploy",
            "appId": "my-app",
            "userId": "admin",
            "permitted": True,
            "timestamp": "2025-01-15T12:00:00Z",
            "source": "cli",
            "entryHash": "abc123",
        }
        entry = AuditEntry.model_validate(data)
        assert entry.action == "Deploy"
        assert entry.app_id == "my-app"
        assert entry.user_id == "admin"
        assert entry.permitted is True
        assert entry.entry_hash == "abc123"


class TestUserRolesResponse:
    """Tests for the UserRolesResponse model."""

    def test_roles(self) -> None:
        data = {"userId": "admin", "roles": ["admin", "deployer"]}
        resp = UserRolesResponse.model_validate(data)
        assert resp.user_id == "admin"
        assert resp.roles == ["admin", "deployer"]

    def test_roles_without_user_id(self) -> None:
        data = {"roles": ["admin", "deployer"]}
        resp = UserRolesResponse.model_validate(data)
        assert resp.user_id is None
        assert resp.roles == ["admin", "deployer"]


class TestIpcErrorResponse:
    """Tests for the IpcErrorResponse model."""

    def test_error(self) -> None:
        data = {"status": 404, "message": "Not found", "detail": "Key missing"}
        resp = IpcErrorResponse.model_validate(data)
        assert resp.status == 404
        assert resp.message == "Not found"
        assert resp.detail == "Key missing"

    def test_error_no_detail(self) -> None:
        data = {"status": 500, "message": "Internal error"}
        resp = IpcErrorResponse.model_validate(data)
        assert resp.detail is None
