# CLAUDE.md - `auragrid-py`

## Overview
`auragrid-py` (Python package `auragrid` v4.3.0) is the standalone Python SDK for building, packaging, and running AuraGrid and AuraSprout Multi-Agent Services (MAS).

It implements the wire contracts and schemas published in sibling repository `auragrid-api` (`../auragrid-api`).

## Architecture & Key Modules
- `auragrid/grid_context.py`: `GridContext` and `AsyncGridContext` unified facade (`config`, `membership`, `governance`, `events`, `storage`, `lease`, `collaboration`, `registry`, `chaos`).
- `auragrid/collaboration.py`: `CollaborationClient`, `AsyncCollaborationClient`, `MasPlacementMode` (`LocalOnly`, `CellSingleton`, `Distributed`), `ConflictResolutionAction`, `LeaseRecordDto`, `WorkBatchClaimDto`, `LeaseConflictDto`, and `ConflictError`. Includes HTTP `404`/`501` fallback when running against headless enterprise AuraGrid nodes.
- `auragrid/ipc.py`: `IpcClient`, `AsyncIpcClient`, `IpcOptions` (with stdin/env token handshake), `IpcError`.
- `auragrid/emulation.py`: `EmulatedIpcClient` / `AsyncEmulatedIpcClient` offline simulator for unit testing without an active node daemon.
- `auragrid/service_server.py`: Embedded `ThreadingHTTPServer` host for `@auragrid_service` Python endpoints.
- `auragrid/cli.py`: Developer CLI (`auragrid validate`, `auragrid pack`, `auragrid init`, `auragrid run`, `auragrid status`, `auragrid apps`, `auragrid pki`).

## Development Commands
```powershell
pip install --no-build-isolation --no-deps -e C:\projects\auracore\auragrid-api
pip install --no-build-isolation --no-deps -e C:\projects\auracore\auragrid-py
pytest tests/ -v
```

## Contract & Quality Gates
- Wire schemas and golden payloads live in `auragrid-api`. Never drift field names or enum values.
- Placement mode enum is strictly `{ LocalOnly, CellSingleton, Distributed }`.
