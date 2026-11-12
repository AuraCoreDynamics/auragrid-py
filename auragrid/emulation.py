"""Standalone in-memory emulation layer for AuraGrid Python SDK.

Provides full in-memory simulation of cell configuration, membership,
leases, storage, governance, collaboration, and events. Enables running and
unit-testing Python MAS applications locally or offline without a running
AuraGrid or AuraSprout daemon.
"""

from __future__ import annotations

import datetime
import getpass
import logging
import os
import socket
import uuid
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import httpx

logger = logging.getLogger("auragrid.emulation")


class EmulatedIpcClient:
    """Synchronous in-memory emulation of the AuraGrid IPC bridge."""

    def __init__(self, node_id: str = "emulated-local-node") -> None:
        self.node_id = node_id
        self._closed = False
        emulated_host = os.environ.get("AURAGRID_EMULATED_HOST", "127.0.0.1")
        emulated_port = int(os.environ.get("AURAGRID_EMULATED_PORT", "0"))
        self._config: dict[str, Any] = {
            "filesystem/grid-root": "./.grid-storage",
            "node/id": self.node_id,
            "cell/id": "cell-local",
            "environment": "standalone-dev",
        }
        self._members: dict[str, dict[str, Any]] = {
            self.node_id: {
                "nodeId": self.node_id,
                "hostName": socket.gethostname() or "local-workstation",
                "hostname": socket.gethostname() or "local-workstation",
                "address": f"{emulated_host}:{emulated_port}",
                "ipAddress": emulated_host,
                "port": emulated_port,
                "state": "Healthy",
                "status": "Healthy",
                "roles": ["Worker", "Host", "Genesis"],
                "capabilities": {"cpu_threads": 8, "ram_mb": 16384},
                "lastHeartbeat": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        }
        self._leases: dict[str, dict[str, Any]] = {}
        self._fencing_counters: dict[str, int] = {}
        self._batches: dict[str, dict[str, Any]] = {}
        self._conflicts: dict[str, dict[str, Any]] = {}
        self._storage: dict[str, bytes] = {}
        self._events: list[dict[str, Any]] = []

    def __enter__(self) -> EmulatedIpcClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        """Mark the emulated IPC session as closed and release transient buffers."""
        self._closed = True

    def set_config(self, key: str, value: Any) -> None:
        """Set a simulated configuration value."""
        self._config[key] = value

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a simulated configuration value."""
        return self._config.get(key, default)

    def _next_fencing_token(self, mas_id: str) -> int:
        next_token = self._fencing_counters.get(mas_id, 0) + 1
        self._fencing_counters[mas_id] = next_token
        return next_token

    def _ensure_lease_record(self, mas_id: str, user: Optional[str] = None) -> dict[str, Any]:
        existing = self._leases.get(mas_id)
        if existing is not None:
            return existing
        now = datetime.datetime.now(datetime.timezone.utc)
        expires = now + datetime.timedelta(seconds=60)
        record = {
            "masId": mas_id,
            "mode": "CellSingleton",
            "holderNodeId": self.node_id,
            "holderUser": user or getpass.getuser(),
            "holderHostName": socket.gethostname() or "local-workstation",
            "fencingToken": self._next_fencing_token(mas_id),
            "acquiredAt": now.isoformat(),
            "expiresAt": expires.isoformat(),
            "lastKnownMarker": None,
            "pid": os.getpid(),
            "volunteerEnabled": False,
            "activitySummary": "Standalone emulated session",
            "progressPct": 0.0,
            "lastCheckpointUtc": now.isoformat(),
            "state": "Standby",
        }
        self._leases[mas_id] = record
        return record

    def _route(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json: Optional[Any] = None,
        data: Optional[Any] = None,
        content: Optional[Any] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        parsed = urlparse(path)
        norm_path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)
        if params:
            for k, v in params.items():
                query[k] = [str(v)]

        if content is not None and data is None:
            data = content

        req = httpx.Request(method, f"http://emulated-ipc{path}")

        # 1. Config endpoints
        if norm_path == "/cell/config":
            if method == "GET":
                return httpx.Response(200, json={"config": dict(self._config)}, request=req)
            if method == "POST" and isinstance(json, dict):
                self._config.update(json)
                return httpx.Response(200, json={"updated": True}, request=req)

        if norm_path.startswith("/cell/config/"):
            key = norm_path[len("/cell/config/") :]
            if method == "GET":
                val = self._config.get(key)
                return httpx.Response(200, json={"key": key, "value": val}, request=req)
            if method in ("PUT", "POST"):
                val = json.get("value") if isinstance(json, dict) and "value" in json else (json if json is not None else data)
                self._config[key] = val
                return httpx.Response(200, json={"key": key, "value": val}, request=req)

        # 2. Membership endpoints
        if norm_path == "/cell/local-node":
            return httpx.Response(200, json=self._members[self.node_id], request=req)

        if norm_path == "/cell/members":
            return httpx.Response(200, json={"members": list(self._members.values())}, request=req)

        if norm_path == "/cell/members/count" or norm_path == "/cell/members/_healthy-count":
            return httpx.Response(200, json={"count": len(self._members)}, request=req)

        if norm_path.startswith("/cell/members/"):
            m_id = norm_path[len("/cell/members/") :]
            member = self._members.get(m_id)
            if member:
                return httpx.Response(200, json=member, request=req)
            return httpx.Response(404, json={}, request=req)

        # 3. Governance endpoints
        if norm_path.startswith("/cell/governance/"):
            return httpx.Response(
                200,
                json={
                    "isPermitted": True,
                    "isAllowed": True,
                    "allowed": True,
                    "decision": "Allow",
                    "reason": "Standalone emulation mode permit",
                },
                request=req,
            )

        # 4. Collaboration endpoints
        if norm_path.startswith("/cell/collaboration/status/"):
            mas_id = norm_path[len("/cell/collaboration/status/") :]
            record = self._ensure_lease_record(mas_id)
            return httpx.Response(200, json=record, request=req)

        if norm_path == "/cell/collaboration/volunteer" and method == "POST":
            body = json if isinstance(json, dict) else {}
            mas_id = body.get("masId", "default-mas")
            enabled = bool(body.get("enabled", False))
            user = body.get("user")
            record = self._ensure_lease_record(mas_id, user=user)
            now = datetime.datetime.now(datetime.timezone.utc)
            record["volunteerEnabled"] = enabled
            record["state"] = "Active" if enabled else "Standby"
            if enabled:
                record["fencingToken"] = self._next_fencing_token(mas_id)
                record["acquiredAt"] = now.isoformat()
                record["expiresAt"] = (now + datetime.timedelta(seconds=60)).isoformat()
            return httpx.Response(200, json=record, request=req)

        if norm_path == "/cell/collaboration/batches/claim" and method == "POST":
            body = json if isinstance(json, dict) else {}
            mas_id = body.get("masId", "default-mas")
            item_ids = list(body.get("itemIds", []))
            ttl_seconds = float(body.get("ttlSeconds", 60.0))
            lease = self._ensure_lease_record(mas_id)
            now = datetime.datetime.now(datetime.timezone.utc)
            batch_id = f"batch-{uuid.uuid4().hex[:12]}"
            claim = {
                "batchId": batch_id,
                "masId": mas_id,
                "claimedByNodeId": self.node_id,
                "claimedByUser": lease["holderUser"],
                "claimedAtUtc": now.isoformat(),
                "expiresAtUtc": (now + datetime.timedelta(seconds=ttl_seconds)).isoformat(),
                "itemIds": item_ids,
                "status": "Claimed",
                "fencingToken": lease["fencingToken"],
                "checkpointMetadata": None,
            }
            self._batches[batch_id] = claim
            return httpx.Response(200, json=claim, request=req)

        if norm_path.startswith("/cell/collaboration/batches/") and norm_path.endswith("/commit") and method == "POST":
            parts = norm_path.split("/")
            batch_id = parts[4] if len(parts) >= 6 else ""
            claim = self._batches.get(batch_id)
            if claim is None:
                return httpx.Response(404, json={"error": "Batch not found", "batchId": batch_id}, request=req)
            body = json if isinstance(json, dict) else {}
            fencing_token = int(body.get("fencingToken", 0))
            lease = self._ensure_lease_record(claim["masId"])
            expected_token = int(lease["fencingToken"])
            if fencing_token != expected_token:
                conflict_id = f"conflict-{uuid.uuid4().hex[:10]}"
                conflict = {
                    "conflictId": conflict_id,
                    "masId": claim["masId"],
                    "localNodeId": self.node_id,
                    "localFencingToken": fencing_token,
                    "remoteHolderNodeId": lease["holderNodeId"],
                    "remoteHolderUser": lease["holderUser"],
                    "remoteFencingToken": expected_token,
                    "uncommittedItemCount": len(claim.get("itemIds", [])),
                    "detectedAtUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "availableResolutions": [
                        "DiscardLocalAndSync",
                        "KeepLocalAndStageMerge",
                        "TakeOverStaleLock",
                        "YieldToPeer",
                    ],
                }
                self._conflicts[conflict_id] = conflict
                lease["state"] = "ConflictPending"
                return httpx.Response(409, json=conflict, request=req)

            claim["status"] = "Committed"
            if body.get("checkpointMetadata") is not None:
                claim["checkpointMetadata"] = body["checkpointMetadata"]
            lease["lastCheckpointUtc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            return httpx.Response(200, json=claim, request=req)

        if norm_path == "/cell/collaboration/conflicts" and method == "GET":
            mas_filter = query.get("masId", [None])[0]
            conflicts = [
                c for c in self._conflicts.values()
                if mas_filter is None or c["masId"] == mas_filter
            ]
            return httpx.Response(200, json={"conflicts": conflicts}, request=req)

        if norm_path.startswith("/cell/collaboration/conflicts/") and norm_path.endswith("/resolve") and method == "POST":
            parts = norm_path.split("/")
            conflict_id = parts[4] if len(parts) >= 6 else ""
            conflict = self._conflicts.pop(conflict_id, None)
            if conflict is None:
                return httpx.Response(404, json={"error": "Conflict not found"}, request=req)
            body = json if isinstance(json, dict) else {}
            action = body.get("action", "DiscardLocalAndSync")
            lease = self._ensure_lease_record(conflict["masId"])
            now = datetime.datetime.now(datetime.timezone.utc)
            if action == "TakeOverStaleLock":
                lease["fencingToken"] = self._next_fencing_token(conflict["masId"])
                lease["state"] = "Active"
                lease["acquiredAt"] = now.isoformat()
                lease["expiresAt"] = (now + datetime.timedelta(seconds=60)).isoformat()
            elif action == "YieldToPeer":
                lease["state"] = "Standby"
                lease["volunteerEnabled"] = False
            else:
                lease["state"] = "Active"
            return httpx.Response(200, json=lease, request=req)

        # 5. Lease endpoints (/cell/lease/* and legacy /leases/*)
        if norm_path == "/cell/lease/acquire" and method == "POST":
            body = json if isinstance(json, dict) else {}
            mas_id = body.get("masId", "default-mas")
            lease = self._ensure_lease_record(mas_id)
            now = datetime.datetime.now(datetime.timezone.utc)
            lease["fencingToken"] = self._next_fencing_token(mas_id)
            lease["acquiredAt"] = now.isoformat()
            lease["expiresAt"] = (now + datetime.timedelta(seconds=60)).isoformat()
            lease["state"] = "Active"
            return httpx.Response(200, json={"acquired": True, "lease": lease, "reason": None}, request=req)

        if norm_path == "/cell/lease/renew" and method == "POST":
            body = json if isinstance(json, dict) else {}
            mas_id = body.get("masId", "default-mas")
            lease = self._leases.get(mas_id)
            if lease is None or int(body.get("fencingToken", 0)) != int(lease["fencingToken"]):
                return httpx.Response(200, json={"extended": False, "conflict": None}, request=req)
            lease["expiresAt"] = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=60)).isoformat()
            if body.get("marker") is not None:
                lease["lastKnownMarker"] = body["marker"]
            return httpx.Response(200, json={"extended": True, "conflict": None}, request=req)

        if norm_path == "/cell/lease/release" and method == "POST":
            body = json if isinstance(json, dict) else {}
            mas_id = body.get("masId", "default-mas")
            self._leases.pop(mas_id, None)
            return httpx.Response(204, request=req)

        if norm_path.startswith("/cell/lease/marker/"):
            mas_id = norm_path[len("/cell/lease/marker/") :]
            lease = self._leases.get(mas_id)
            marker = lease.get("lastKnownMarker") if lease else None
            return httpx.Response(200, json={"marker": marker}, request=req)

        if norm_path.startswith("/cell/lease/"):
            mas_id = norm_path[len("/cell/lease/") :]
            lease = self._leases.get(mas_id)
            if lease is None:
                return httpx.Response(404, json={"error": "Lease not found", "masId": mas_id}, request=req)
            return httpx.Response(200, json=lease, request=req)

        if "/leases" in norm_path:
            parts = norm_path.split("/")
            mas_id = parts[3] if len(parts) > 3 else "default-mas"
            now = datetime.datetime.now(datetime.timezone.utc)
            expires = now + datetime.timedelta(seconds=60)
            lease_data = {
                "masId": mas_id,
                "holderNodeId": self.node_id,
                "fencingToken": 1,
                "granted": True,
                "acquiredAt": now.isoformat(),
                "expiresAt": expires.isoformat(),
            }
            self._leases[mas_id] = lease_data
            if norm_path.endswith("/acquire"):
                return httpx.Response(200, json=lease_data, request=req)
            if norm_path.endswith("/renew"):
                return httpx.Response(200, json={"renewed": True, **lease_data}, request=req)
            if norm_path.endswith("/release"):
                self._leases.pop(mas_id, None)
                return httpx.Response(200, json={"released": True}, request=req)
            return httpx.Response(200, json=lease_data, request=req)

        # 6. Storage endpoints
        if norm_path == "/cell/storage/write":
            p = query.get("path", [""])[0] or (json.get("path") if isinstance(json, dict) else "")
            payload = data or (json.get("content") if isinstance(json, dict) else b"")
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            self._storage[p] = payload
            return httpx.Response(200, json={"written": True, "size": len(payload)}, request=req)

        if norm_path in ("/cell/storage/read", "/cell/storage/range"):
            p = query.get("path", [""])[0]
            stored_content = self._storage.get(p)
            if stored_content is None:
                return httpx.Response(404, text="Not Found", request=req)
            if norm_path == "/cell/storage/range":
                offset = int(query.get("offset", [0])[0])
                count = int(query.get("count", [len(stored_content)])[0])
                slice_bytes = stored_content[offset : offset + count]
                return httpx.Response(200, content=slice_bytes, request=req)
            return httpx.Response(200, content=stored_content, request=req)

        if norm_path == "/cell/storage/exists":
            p = query.get("path", [""])[0]
            return httpx.Response(200, json={"exists": p in self._storage}, request=req)

        if norm_path.startswith("/cell/storage/"):
            sub = norm_path[len("/cell/storage/") :]
            if sub not in ("write", "read", "exists", "range", "list", "delete"):
                if method in ("PUT", "POST"):
                    payload = data if data is not None else (json.encode("utf-8") if isinstance(json, str) else b"")
                    self._storage[sub] = payload
                    return httpx.Response(200, json={"written": True, "size": len(payload)}, request=req)
                if method == "GET":
                    stored_content = self._storage.get(sub)
                    if stored_content is None:
                        return httpx.Response(404, text="Not Found", request=req)
                    return httpx.Response(200, content=stored_content, request=req)
                if method == "DELETE":
                    self._storage.pop(sub, None)
                    return httpx.Response(200, json={"deleted": True}, request=req)

        # 7. Events endpoints
        if norm_path.startswith("/cell/events") or norm_path.startswith("/events"):
            topic_id = norm_path.split("/")[-1] if "/" in norm_path else "default"
            if method == "POST":
                req_data = json if isinstance(json, dict) else {}
                b64_payload = req_data.get("payload", "")
                event_type = req_data.get("eventType")
                seq = len(self._events) + 1
                event_dict = {
                    "eventId": str(uuid.uuid4()),
                    "topicId": topic_id,
                    "sequenceNumber": seq,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "sourceNodeId": self.node_id,
                    "eventType": event_type,
                    "payload": b64_payload,
                }
                self._events.append(event_dict)
                return httpx.Response(200, json=event_dict, request=req)
            return httpx.Response(200, json={"events": self._events}, request=req)

        # Fallback default response
        return httpx.Response(200, json={"status": "ok", "emulated": True}, request=req)

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._route("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._route("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._route("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._route("DELETE", path, **kwargs)


class AsyncEmulatedIpcClient(EmulatedIpcClient):
    """Asynchronous in-memory emulation of the AuraGrid IPC bridge."""

    async def __aenter__(self) -> AsyncEmulatedIpcClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Mark the async emulated IPC session as closed."""
        self._closed = True

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._route("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._route("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._route("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._route("DELETE", path, **kwargs)
