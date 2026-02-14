# AuraGrid Python SDK - Cell API Client

The AuraGrid Python SDK provides Python MAS (Managed Application Service) applications with IPC access to cell-level services: **configuration**, **membership**, and **governance**. Both synchronous and asynchronous APIs are available.

## Installation

```bash
pip install auragrid
# or for development
pip install -e ".[dev]"
```

### Dependencies

- `httpx>=0.27` - HTTP transport with sync and async support
- `pydantic>=2.0` - Validated data models with JSON serialization

## Quick Start

### Synchronous Usage

```python
from auragrid import GridContext

with GridContext() as ctx:
    # Configuration
    value = ctx.config.get("filesystem/grid-root")
    ctx.config.set("my-key", "my-value")
    all_config = ctx.config.get_all()

    # Membership
    members = ctx.membership.get_members()
    local = ctx.membership.get_local_node()
    healthy = ctx.membership.get_healthy_count()

    # Governance
    decision = ctx.governance.can_deploy("my-app", "admin")
    if decision.is_permitted:
        print("Deployment allowed")
    roles = ctx.governance.get_user_roles("admin")
```

### Asynchronous Usage

```python
import asyncio
from auragrid import AsyncGridContext

async def main():
    async with AsyncGridContext() as ctx:
        # Configuration
        value = await ctx.config.get("filesystem/grid-root")
        await ctx.config.set("my-key", "my-value")

        # Watch for changes
        async for new_value in ctx.config.watch("my-key", interval=2.0):
            print(f"Config changed: {new_value}")

        # Membership
        members = await ctx.membership.get_members()
        local = await ctx.membership.get_local_node()

        # Governance
        decision = await ctx.governance.can_deploy("my-app", "admin")
        audit = await ctx.governance.get_audit_trail(limit=50)

asyncio.run(main())
```

## Environment Variables

The SDK reads the following environment variables automatically:

| Variable | Description | Default |
|----------|-------------|---------|
| `AURAGRID_IPC_PORT` | Port number of the local IPC bridge | `5100` |
| `AURAGRID_IPC_TOKEN` | Shared secret for IPC authentication | `""` |
| `AURAGRID_MAS_ID` | MAS application ID assigned by the grid | `None` |
| `AURAGRID_NODE_ID` | Local node ID in the cell | `None` |
| `AURAGRID_FENCING_TOKEN` | Fencing token for split-brain protection | `None` |

## IPC Options

Customize connection settings via `IpcOptions`:

```python
from auragrid import GridContext, IpcOptions

options = IpcOptions(
    port=5200,
    token="my-secret-token",
    timeout=10.0,       # request timeout in seconds
    max_retries=3,      # retry attempts on transient errors
    backoff_factor=1.0,  # exponential backoff multiplier
)

with GridContext(options) as ctx:
    ...
```

## Cell Configuration

Read and write cell-level configuration that is synchronized across all nodes via gossip protocol.

### Sync API: `CellConfiguration`

```python
from auragrid import GridContext

with GridContext() as ctx:
    # Get a single value
    value = ctx.config.get("filesystem/grid-root")  # returns None if missing

    # Get all configuration
    all_config = ctx.config.get_all()  # returns dict[str, Any]

    # Set a value (propagated via gossip)
    ctx.config.set("my-key", {"nested": "value"})

    # Remove a key
    removed = ctx.config.remove("my-key")  # returns bool

    # Get metadata
    meta = ctx.config.get_metadata()
    print(f"Keys: {meta.key_count}, Version: {meta.max_version}")
```

### Async API: `AsyncCellConfiguration`

All methods from the sync API are available as coroutines, plus `watch()`:

```python
from auragrid import AsyncGridContext

async with AsyncGridContext() as ctx:
    # Watch for changes (async generator)
    async for value in ctx.config.watch("my-key", interval=2.0):
        print(f"New value: {value}")
```

## Cell Membership

Query the SWIM-gossip-backed membership list to discover nodes in the cell.

### Sync API: `CellMembership`

```python
from auragrid import GridContext

with GridContext() as ctx:
    # List members
    members = ctx.membership.get_members()
    members_all = ctx.membership.get_members(include_unhealthy=True)

    # Get specific member
    member = ctx.membership.get_member("node-1")  # returns None if not found

    # Local node
    local = ctx.membership.get_local_node()
    node_id = ctx.membership.local_node_id  # cached property

    # Health
    healthy = ctx.membership.get_healthy_count()

    # Metadata
    meta = ctx.membership.get_metadata()
    print(f"Protocol: {meta.protocol}, Healthy: {meta.healthy_count}/{meta.total_count}")
```

### Async API: `AsyncCellMembership`

Same methods available as coroutines. The `local_node_id` property returns `None` until `get_local_node()` has been called.

## Governance

Query RBAC policies, check deployment permissions, and read the audit trail.

### Sync API: `GovernanceClient`

```python
from auragrid import GridContext

with GridContext() as ctx:
    # Permission checks
    decision = ctx.governance.can_deploy("my-app", "admin")
    if decision.is_permitted:
        print("Allowed")
    else:
        print(f"Denied: {decision.deny_reason}")

    decision = ctx.governance.can_remove("old-app", "admin")
    decision = ctx.governance.can_reconfigure("my-app", "admin")

    # User roles
    roles = ctx.governance.get_user_roles("admin")
    print(f"Roles: {roles}")

    # Audit trail
    entries = ctx.governance.get_audit_trail(limit=50)
    for entry in entries:
        print(f"{entry.action} {entry.app_id} by {entry.user_id}: {'OK' if entry.permitted else 'DENIED'}")
```

### Async API: `AsyncGovernanceClient`

All methods available as coroutines.

## Models

All models use Pydantic `BaseModel` with `ConfigDict(populate_by_name=True)` and camelCase aliases for JSON interop.

### CellMember

| Field | Type | Alias | Description |
|-------|------|-------|-------------|
| `node_id` | `str` | `nodeId` | Unique node identifier |
| `host_name` | `str?` | `hostName` | Human-readable hostname |
| `state` | `str` | `state` | Health state (Alive/Suspected/Dead) |
| `address` | `str?` | `address` | Network address |
| `joined_at` | `datetime?` | `joinedAt` | When the node joined |
| `last_heartbeat` | `datetime` | `lastHeartbeat` | Last heartbeat time |
| `registered_services` | `list[str]?` | `registeredServices` | Registered service names |
| `metadata` | `dict[str,str]?` | `metadata` | Custom tags |
| `incarnation` | `int` | `incarnation` | Version number |

### CellMembershipMetadata

| Field | Type | Alias | Description |
|-------|------|-------|-------------|
| `healthy_count` | `int` | `healthyCount` | Healthy member count |
| `total_count` | `int` | `totalCount` | Total member count |
| `last_updated` | `datetime` | `lastUpdated` | Last update time |
| `incarnation_number` | `int` | `incarnationNumber` | Incarnation number |
| `protocol` | `str?` | `protocol` | Protocol name (e.g., SWIM) |

### CellConfigMetadata

| Field | Type | Alias | Description |
|-------|------|-------|-------------|
| `key_count` | `int` | `keyCount` | Number of config keys |
| `max_version` | `int` | `maxVersion` | Max version number |
| `last_modified` | `datetime` | `lastModified` | Last modification time |
| `last_modified_by_node_id` | `str?` | `lastModifiedByNodeId` | Node that last modified |
| `synchronized_node_count` | `int` | `synchronizedNodeCount` | Synced node count |
| `storage_path` | `str?` | `storagePath` | Storage file path |

### GovernanceDecision

| Field | Type | Alias | Description |
|-------|------|-------|-------------|
| `is_permitted` | `bool` | `isPermitted` | Whether action is allowed |
| `deny_reason` | `str?` | `denyReason` | Reason for denial |
| `requires_approval` | `bool` | `requiresApproval` | Needs human approval |
| `metadata` | `dict[str,str]?` | `metadata` | Additional context |
| `expires_at` | `datetime?` | `expiresAt` | Decision expiry |

### AuditEntry

| Field | Type | Alias | Description |
|-------|------|-------|-------------|
| `action` | `str` | `action` | Action type (Deploy/Remove/etc.) |
| `app_id` | `str` | `appId` | Application identifier |
| `user_id` | `str` | `userId` | User who performed action |
| `permitted` | `bool` | `permitted` | Whether action was allowed |
| `deny_reason` | `str?` | `denyReason` | Denial reason |
| `timestamp` | `datetime` | `timestamp` | When action occurred |
| `source` | `str?` | `source` | Request source |
| `entry_hash` | `str?` | `entryHash` | SHA-256 hash chain entry |

### UserRolesResponse

| Field | Type | Alias | Description |
|-------|------|-------|-------------|
| `user_id` | `str` | `userId` | User identifier |
| `roles` | `list[str]` | `roles` | Assigned roles |

### IpcErrorResponse

| Field | Type | Alias | Description |
|-------|------|-------|-------------|
| `status` | `int` | `status` | HTTP status code |
| `message` | `str` | `message` | Error message |
| `detail` | `str?` | `detail` | Additional detail |

## Error Handling

All IPC errors raise `IpcError`:

```python
from auragrid import GridContext, IpcError

with GridContext() as ctx:
    try:
        value = ctx.config.get("some-key")
    except IpcError as e:
        print(f"IPC error {e.status_code}: {e.message}")
```

### Retry Behavior

The IPC client automatically retries on:
- HTTP 5xx status codes (server errors)
- `httpx.TransportError` (connection failures)

Retries use exponential backoff: `backoff_factor * (2 ** attempt)`. The default is 2 retries with a 0.5s backoff factor, giving delays of 0.5s and 1.0s. HTTP 4xx errors are never retried.

## Grid Context Properties

```python
with GridContext() as ctx:
    ctx.mas_id          # AURAGRID_MAS_ID env var (str or None)
    ctx.node_id         # AURAGRID_NODE_ID env var (str or None)
    ctx.fencing_token   # AURAGRID_FENCING_TOKEN env var (str or None)
    ctx.is_connected    # True if IPC bridge responds to health check
```

## Testing

```bash
cd src/AuraGrid.PythonSdk
pip install -e ".[dev]"
pytest tests/
```

Tests use `httpx.MockTransport` for HTTP mocking and do not require a running IPC bridge.
