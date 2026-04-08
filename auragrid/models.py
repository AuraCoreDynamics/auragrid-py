"""Pydantic data models for AuraGrid IPC cell API responses.

These DTOs mirror the C# records in ``AuraGrid.Abstractions.Configuration``
and ``AuraGrid.Abstractions.Governance``, using camelCase JSON aliases for
seamless interop with the .NET IPC bridge.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Cell Membership models
# ---------------------------------------------------------------------------


class CellMember(BaseModel):
    """Information about a node in the cell.

    Mirrors C# ``CellMember`` from ``AuraGrid.Abstractions.Configuration``.
    """

    model_config = ConfigDict(populate_by_name=True)

    node_id: str = Field(alias="nodeId")
    host_name: Optional[str] = Field(default=None, alias="hostName")
    state: str = Field(alias="state")
    address: Optional[str] = Field(default=None, alias="address")
    joined_at: Optional[datetime] = Field(default=None, alias="joinedAt")
    last_heartbeat: datetime = Field(alias="lastHeartbeat")
    registered_services: Optional[list[str]] = Field(
        default=None, alias="registeredServices"
    )
    metadata: Optional[dict[str, str]] = Field(default=None, alias="metadata")
    incarnation: int = Field(default=0, alias="incarnation")


class CellMembershipMetadata(BaseModel):
    """Metadata about the membership system state.

    Mirrors C# ``CellMembershipMetadata``.
    """

    model_config = ConfigDict(populate_by_name=True)

    healthy_count: int = Field(alias="healthyCount")
    total_count: int = Field(alias="totalCount")
    last_updated: datetime = Field(alias="lastUpdated")
    incarnation_number: int = Field(alias="incarnationNumber")
    protocol: Optional[str] = Field(default=None, alias="protocol")


class CellMembersResponse(BaseModel):
    """Response wrapper for a list of cell members."""

    model_config = ConfigDict(populate_by_name=True)

    members: list[CellMember] = Field(alias="members")


# ---------------------------------------------------------------------------
# Cell Configuration models
# ---------------------------------------------------------------------------


class CellConfigMetadata(BaseModel):
    """Metadata about cell configuration state.

    Mirrors C# ``CellConfigurationMetadata``.
    """

    model_config = ConfigDict(populate_by_name=True)

    key_count: int = Field(alias="keyCount")
    max_version: int = Field(alias="maxVersion")
    last_modified: datetime = Field(alias="lastModified")
    last_modified_by_node_id: Optional[str] = Field(
        default=None, alias="lastModifiedByNodeId"
    )
    synchronized_node_count: int = Field(default=0, alias="synchronizedNodeCount")
    storage_path: Optional[str] = Field(default=None, alias="storagePath")


class CellConfigAllResponse(BaseModel):
    """Response wrapper for all configuration key-value pairs."""

    model_config = ConfigDict(populate_by_name=True)

    config: dict[str, Any] = Field(alias="config")


class CellConfigValueResponse(BaseModel):
    """Response from GET /cell/config/{key}."""

    value: Any


# ---------------------------------------------------------------------------
# Governance models
# ---------------------------------------------------------------------------


class GovernanceDecision(BaseModel):
    """Result of a governance decision.

    Mirrors C# ``GovernanceDecision``.
    """

    model_config = ConfigDict(populate_by_name=True)

    is_permitted: bool = Field(alias="isPermitted")
    deny_reason: Optional[str] = Field(default=None, alias="denyReason")
    requires_approval: bool = Field(default=False, alias="requiresApproval")
    metadata: Optional[dict[str, str]] = Field(default=None, alias="metadata")
    expires_at: Optional[datetime] = Field(default=None, alias="expiresAt")


class AuditEntry(BaseModel):
    """Audit entry for governance events.

    Mirrors C# ``GovernanceAuditEntry``.
    """

    model_config = ConfigDict(populate_by_name=True)

    action: str = Field(alias="action")
    app_id: str = Field(alias="appId")
    user_id: str = Field(alias="userId")
    permitted: bool = Field(alias="permitted")
    deny_reason: Optional[str] = Field(default=None, alias="denyReason")
    timestamp: datetime = Field(alias="timestamp")
    source: Optional[str] = Field(default=None, alias="source")
    entry_hash: Optional[str] = Field(default=None, alias="entryHash")


class UserRolesResponse(BaseModel):
    """Response wrapper for user roles."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str | None = Field(default=None, alias="userId")
    roles: list[str] = Field(alias="roles")


# ---------------------------------------------------------------------------
# Error model
# ---------------------------------------------------------------------------


class IpcErrorResponse(BaseModel):
    """Standard error response from the IPC bridge."""

    model_config = ConfigDict(populate_by_name=True)

    status: int = Field(alias="status")
    message: str = Field(alias="message")
    detail: Optional[str] = Field(default=None, alias="detail")

