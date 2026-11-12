# `auragrid-py` (`auragrid`)

Standalone Python SDK for **AuraGrid** and **AuraSprout** Multi-Agent Services (MAS).

## Installation

```bash
pip install -e ../auragrid-api
pip install -e .
```

## Highlights (v4.3.0)

- Extracted from `auragrid` monorepo into a sovereign Python SDK package (`auragrid`).
- Aligned with canonical JSON Schemas and OpenAPI contracts in `auragrid-api`.
- Added `CollaborationClient` / `AsyncCollaborationClient` (`ctx.collaboration`) supporting:
  - Opt-in volunteer toggles (`set_volunteer_enabled`)
  - Distributed batch claiming & fenced staged commits (`claim_work_batch`, `commit_work_batch`)
  - Conflict listing & resolution (`list_conflicts`, `resolve_conflict`)
  - Automatic HTTP `404`/`501` pass-through fallback on headless enterprise `AuraGrid` nodes
- Unified `MasPlacementMode` (`LocalOnly`, `CellSingleton`, `Distributed`).
- Upgraded `ServiceServer` to `ThreadingHTTPServer` with ephemeral loopback binding (`127.0.0.1:0` default).

## Running Tests

```bash
pytest tests/ -v
```
