"""AuraGrid Python SDK - decorators, descriptor generation, lifecycle, and IPC cell API client for Python MAS."""

from .cell_config import AsyncCellConfiguration, CellConfiguration
from .cell_membership import AsyncCellMembership, CellMembership
from .decorators import auragrid_method, auragrid_service
from .descriptor import generate_descriptor, save_descriptor
from .governance import AsyncGovernanceClient, GovernanceClient
from .grid_context import AsyncGridContext, GridContext
from .ipc import AsyncIpcClient, IpcClient, IpcError, IpcOptions
from .lifecycle import LifecycleCallback, LifecycleContext, LifecyclePhase
from .service_server import ServiceServer
from .models import (
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

__all__ = [
    # Decorators
    "auragrid_service",
    "auragrid_method",
    # Descriptor generation
    "generate_descriptor",
    "save_descriptor",
    # Lifecycle
    "LifecyclePhase",
    "LifecycleContext",
    "LifecycleCallback",
    # IPC client
    "IpcClient",
    "AsyncIpcClient",
    "IpcError",
    "IpcOptions",
    # Cell configuration
    "CellConfiguration",
    "AsyncCellConfiguration",
    # Cell membership
    "CellMembership",
    "AsyncCellMembership",
    # Governance
    "GovernanceClient",
    "AsyncGovernanceClient",
    # Grid context
    "GridContext",
    "AsyncGridContext",
    # Service server
    "ServiceServer",
    # Models
    "CellMember",
    "CellMembershipMetadata",
    "CellMembersResponse",
    "CellConfigMetadata",
    "CellConfigAllResponse",
    "CellConfigValueResponse",
    "GovernanceDecision",
    "AuditEntry",
    "UserRolesResponse",
    "IpcErrorResponse",
]
