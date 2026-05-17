"""AuraGrid Python SDK - decorators, descriptor generation, lifecycle, and IPC cell API client for Python MAS."""

from .cell_config import AsyncCellConfiguration, CellConfiguration
from .cell_membership import AsyncCellMembership, CellMembership
from .chaos_client import AsyncChaosClient, ChaosClient
from .decorators import auragrid_method, auragrid_service
from .descriptor import generate_descriptor, save_descriptor
from .event_client import AsyncEventClient, EventClient
from .event_models import AuraEventDto, ConsumeResponse, PublishRequest, WalMarkerDto
from .governance import AsyncGovernanceClient, GovernanceClient
from .grid_context import AsyncGridContext, GridContext
from .ipc import AsyncIpcClient, IpcClient, IpcError, IpcOptions
from .lease_client import AsyncLeaseClient, LeaseClient
from .lifecycle import LifecycleCallback, LifecycleContext, LifecyclePhase
from .registry_client import AsyncRegistryClient, RegistryClient
from .service_server import ServiceServer
from .storage_client import AsyncStorageClient, StorageClient
from .layer0 import (
    Layer0Client,
    SignatureBlock,
    WasmManifest,
    WasmPayload,
    WasmResult,
    WasmSigner,
)
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
    # Chaos
    "ChaosClient",
    "AsyncChaosClient",
    # Governance
    "GovernanceClient",
    "AsyncGovernanceClient",
    # Eventing
    "EventClient",
    "AsyncEventClient",
    "AuraEventDto",
    "PublishRequest",
    "ConsumeResponse",
    "WalMarkerDto",
    # Grid context
    "GridContext",
    "AsyncGridContext",
    # Lease
    "LeaseClient",
    "AsyncLeaseClient",
    # Registry
    "RegistryClient",
    "AsyncRegistryClient",
    # Storage
    "StorageClient",
    "AsyncStorageClient",
    # Service server
    "ServiceServer",
    # Layer 0
    "WasmSigner",
    "Layer0Client",
    "WasmManifest",
    "WasmPayload",
    "WasmResult",
    "SignatureBlock",
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
