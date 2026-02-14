"""Governance policy client for RBAC and audit trail access.

Provides both synchronous (``GovernanceClient``) and asynchronous
(``AsyncGovernanceClient``) clients that communicate with the IPC bridge
to query governance decisions, user roles, and the audit trail.

Mirrors C# ``IGovernancePolicy`` from
``AuraGrid.Abstractions.Governance``.
"""

from __future__ import annotations

from .ipc import AsyncIpcClient, IpcClient
from .models import AuditEntry, GovernanceDecision, UserRolesResponse


class GovernanceClient:
    """Synchronous client for governance policy queries.

    Args:
        client: An ``IpcClient`` instance for HTTP communication.
    """

    def __init__(self, client: IpcClient) -> None:
        self._client = client

    def can_deploy(self, app_id: str, user_id: str) -> GovernanceDecision:
        """Check if a user has permission to deploy an app.

        Args:
            app_id: Application identifier.
            user_id: User requesting deployment.

        Returns:
            Governance decision with permit/deny and reason.
        """
        response = self._client.post(
            "/cell/governance/can-deploy",
            json={"appId": app_id, "userId": user_id},
        )
        return GovernanceDecision.model_validate(response.json())

    def can_remove(self, app_id: str, user_id: str) -> GovernanceDecision:
        """Check if a user has permission to remove an app.

        Args:
            app_id: Application identifier.
            user_id: User requesting removal.

        Returns:
            Governance decision with permit/deny and reason.
        """
        response = self._client.post(
            "/cell/governance/can-remove",
            json={"appId": app_id, "userId": user_id},
        )
        return GovernanceDecision.model_validate(response.json())

    def can_reconfigure(self, resource_id: str, user_id: str) -> GovernanceDecision:
        """Check if a user has permission to reconfigure a resource.

        Args:
            resource_id: Resource identifier.
            user_id: User requesting reconfiguration.

        Returns:
            Governance decision with permit/deny and reason.
        """
        response = self._client.post(
            "/cell/governance/can-reconfigure",
            json={"resourceId": resource_id, "userId": user_id},
        )
        return GovernanceDecision.model_validate(response.json())

    def get_user_roles(self, user_id: str) -> list[str]:
        """Get the roles assigned to a user.

        Args:
            user_id: User identifier.

        Returns:
            List of role names.
        """
        response = self._client.get(
            f"/cell/governance/roles/{user_id}",
        )
        result = UserRolesResponse.model_validate(response.json())
        return result.roles

    def get_audit_trail(self, limit: int = 100) -> list[AuditEntry]:
        """Get audit trail entries, most recent first.

        Args:
            limit: Maximum number of entries to return (default ``100``).

        Returns:
            List of audit entries ordered by timestamp descending.
        """
        response = self._client.get(
            "/cell/governance/audit",
            params={"limit": limit},
        )
        body = response.json()
        entries = body.get("entries", body) if isinstance(body, dict) else body
        return [AuditEntry.model_validate(entry) for entry in entries]


class AsyncGovernanceClient:
    """Asynchronous client for governance policy queries.

    Args:
        client: An ``AsyncIpcClient`` instance for HTTP communication.
    """

    def __init__(self, client: AsyncIpcClient) -> None:
        self._client = client

    async def can_deploy(self, app_id: str, user_id: str) -> GovernanceDecision:
        """Check if a user has permission to deploy an app.

        Args:
            app_id: Application identifier.
            user_id: User requesting deployment.

        Returns:
            Governance decision with permit/deny and reason.
        """
        response = await self._client.post(
            "/cell/governance/can-deploy",
            json={"appId": app_id, "userId": user_id},
        )
        return GovernanceDecision.model_validate(response.json())

    async def can_remove(self, app_id: str, user_id: str) -> GovernanceDecision:
        """Check if a user has permission to remove an app.

        Args:
            app_id: Application identifier.
            user_id: User requesting removal.

        Returns:
            Governance decision with permit/deny and reason.
        """
        response = await self._client.post(
            "/cell/governance/can-remove",
            json={"appId": app_id, "userId": user_id},
        )
        return GovernanceDecision.model_validate(response.json())

    async def can_reconfigure(self, resource_id: str, user_id: str) -> GovernanceDecision:
        """Check if a user has permission to reconfigure a resource.

        Args:
            resource_id: Resource identifier.
            user_id: User requesting reconfiguration.

        Returns:
            Governance decision with permit/deny and reason.
        """
        response = await self._client.post(
            "/cell/governance/can-reconfigure",
            json={"resourceId": resource_id, "userId": user_id},
        )
        return GovernanceDecision.model_validate(response.json())

    async def get_user_roles(self, user_id: str) -> list[str]:
        """Get the roles assigned to a user.

        Args:
            user_id: User identifier.

        Returns:
            List of role names.
        """
        response = await self._client.get(
            f"/cell/governance/roles/{user_id}",
        )
        result = UserRolesResponse.model_validate(response.json())
        return result.roles

    async def get_audit_trail(self, limit: int = 100) -> list[AuditEntry]:
        """Get audit trail entries, most recent first.

        Args:
            limit: Maximum number of entries to return (default ``100``).

        Returns:
            List of audit entries ordered by timestamp descending.
        """
        response = await self._client.get(
            "/cell/governance/audit",
            params={"limit": limit},
        )
        body = response.json()
        entries = body.get("entries", body) if isinstance(body, dict) else body
        return [AuditEntry.model_validate(entry) for entry in entries]
