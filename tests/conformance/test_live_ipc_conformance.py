"""Live loopback unmocked HTTP IPC conformance tests."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from auragrid import ConflictError, ConflictResolutionAction, GridContext, IpcOptions


class _ReferenceState:
    def __init__(self, expected_token: str) -> None:
        self.expected_token = expected_token
        self.config: dict[str, Any] = {"cell/id": "cell-live-conformance"}
        self.fencing_token = 1
        self.lease = {
            "masId": "live-mas",
            "mode": "CellSingleton",
            "holderNodeId": "live-node-1",
            "holderUser": "conformance-user",
            "holderHostName": "loopback-host",
            "fencingToken": 1,
            "acquiredAt": "2026-11-12T10:00:00Z",
            "expiresAt": "2026-11-12T10:05:00Z",
            "volunteerEnabled": True,
            "state": "Active",
        }
        self.batches: dict[str, dict[str, Any]] = {}
        self.conflicts: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()


def _make_handler(state: _ReferenceState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, code: int, payload: Any) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _auth_ok(self) -> bool:
            token = self.headers.get("X-AuraGrid-IPC-Token", "")
            return token == state.expected_token

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            return json.loads(raw.decode("utf-8"))

        def do_GET(self) -> None:
            if not self._auth_ok():
                self._send_json(401, {"message": "Unauthorized"})
                return
            parsed = urlparse(self.path)
            path = parsed.path
            with state.lock:
                if path == "/api/health":
                    self._send_json(200, {"status": "Healthy"})
                elif path == "/cell/config":
                    self._send_json(200, {"config": dict(state.config)})
                elif path.startswith("/cell/config/"):
                    key = path[len("/cell/config/") :]
                    self._send_json(200, {"key": key, "value": state.config.get(key)})
                elif path.startswith("/cell/collaboration/status/"):
                    self._send_json(200, dict(state.lease))
                elif path == "/cell/collaboration/conflicts":
                    mas_filter = parse_qs(parsed.query).get("masId", [None])[0]
                    items = [
                        c for c in state.conflicts.values()
                        if mas_filter is None or c["masId"] == mas_filter
                    ]
                    self._send_json(200, {"conflicts": items})
                else:
                    self._send_json(404, {"message": "Not Found"})

        def do_POST(self) -> None:
            if not self._auth_ok():
                self._send_json(401, {"message": "Unauthorized"})
                return
            path = urlparse(self.path).path
            body = self._read_json()
            with state.lock:
                if path == "/cell/collaboration/volunteer":
                    state.lease["volunteerEnabled"] = bool(body.get("enabled", True))
                    state.fencing_token += 1
                    state.lease["fencingToken"] = state.fencing_token
                    self._send_json(200, dict(state.lease))
                elif path == "/cell/collaboration/batches/claim":
                    batch_id = f"live-batch-{len(state.batches) + 1}"
                    claim = {
                        "batchId": batch_id,
                        "masId": body["masId"],
                        "claimedByNodeId": "live-node-1",
                        "claimedByUser": "conformance-user",
                        "claimedAtUtc": "2026-11-12T10:00:00Z",
                        "expiresAtUtc": "2026-11-12T10:02:00Z",
                        "itemIds": body["itemIds"],
                        "status": "Claimed",
                        "fencingToken": state.fencing_token,
                        "checkpointMetadata": None,
                    }
                    state.batches[batch_id] = claim
                    self._send_json(200, claim)
                elif path.startswith("/cell/collaboration/batches/") and path.endswith("/commit"):
                    batch_id = path.split("/")[4]
                    claim = state.batches.get(batch_id)
                    if claim is None:
                        self._send_json(404, {"message": "Batch not found"})
                        return
                    token = int(body.get("fencingToken", 0))
                    if token != state.fencing_token:
                        conflict_id = f"live-conflict-{len(state.conflicts) + 1}"
                        conflict = {
                            "conflictId": conflict_id,
                            "masId": claim["masId"],
                            "localNodeId": "live-node-1",
                            "localFencingToken": token,
                            "remoteHolderNodeId": "live-node-2",
                            "remoteHolderUser": "peer-user",
                            "remoteFencingToken": state.fencing_token,
                            "uncommittedItemCount": len(claim["itemIds"]),
                            "detectedAtUtc": "2026-11-12T10:01:00Z",
                            "availableResolutions": ["DiscardLocalAndSync", "TakeOverStaleLock"],
                        }
                        state.conflicts[conflict_id] = conflict
                        state.lease["state"] = "ConflictPending"
                        self._send_json(409, conflict)
                        return
                    claim["status"] = "Committed"
                    claim["checkpointMetadata"] = body.get("checkpointMetadata")
                    self._send_json(200, claim)
                elif path.startswith("/cell/collaboration/conflicts/") and path.endswith("/resolve"):
                    conflict_id = path.split("/")[4]
                    state.conflicts.pop(conflict_id, None)
                    state.fencing_token += 1
                    state.lease["fencingToken"] = state.fencing_token
                    state.lease["state"] = "Active"
                    self._send_json(200, dict(state.lease))
                else:
                    self._send_json(404, {"message": "Not Found"})

    return Handler


@pytest.mark.sovereignty
def test_live_loopback_collaboration_conformance() -> None:
    """Exercise unmocked IpcClient + GridContext against a live ephemeral loopback server."""
    token = "sovereignty-live-token"
    state = _ReferenceState(expected_token=token)
    bind_host = os.environ.get("AURAGRID_TEST_BIND_HOST", "127.0.0.1")
    server = ThreadingHTTPServer((bind_host, 0), _make_handler(state))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        opts = IpcOptions(port=port, token=token, max_retries=0)
        with GridContext(options=opts, standalone=False) as ctx:
            assert ctx.is_connected is True
            assert ctx.config.get("cell/id") == "cell-live-conformance"

            status = ctx.collaboration.set_volunteer_enabled("live-mas", True, user="alice")
            assert status.fencing_token == 2

            batch = ctx.collaboration.claim_work_batch("live-mas", ["k1", "k2"])
            assert batch.fencing_token == 2

            committed = ctx.collaboration.commit_work_batch(
                batch.batch_id,
                fencing_token=2,
                checkpoint_metadata={"offset": "2"},
            )
            assert committed.status == "Committed"

            # Stale fencing token raises ConflictError over real HTTP 409
            stale_batch = ctx.collaboration.claim_work_batch("live-mas", ["k3"])
            with pytest.raises(ConflictError) as exc_info:
                ctx.collaboration.commit_work_batch(stale_batch.batch_id, fencing_token=1)
            assert exc_info.value.conflict is not None

            conflicts = ctx.collaboration.list_conflicts("live-mas")
            assert len(conflicts) == 1
            resolved = ctx.collaboration.resolve_conflict(
                conflicts[0].conflict_id,
                ConflictResolutionAction.TAKE_OVER_STALE_LOCK,
            )
            assert resolved.state == "Active"
            assert resolved.fencing_token == 3
    finally:
        server.shutdown()
        server.server_close()
