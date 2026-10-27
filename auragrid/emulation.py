"""Standalone in-memory emulation layer for AuraGrid Python SDK.

Provides full in-memory simulation of cell configuration, membership,
leases, storage, governance, and events. Enables running and unit-testing
Python MAS applications locally or offline without a running C# AuraGrid daemon.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import httpx

logger = logging.getLogger("auragrid.emulation")


class EmulatedIpcClient:
    """Synchronous in-memory emulation of the AuraGrid IPC bridge."""

    def __init__(self, node_id: str = "emulated-local-node") -> None:
        self.node_id = node_id
        self._config: dict[str, Any] = {
            "filesystem/grid-root": "./.grid-storage",
            "node/id": self.node_id,
            "cell/id": "cell-local",
            "environment": "standalone-dev",
        }
        self._members: dict[str, dict[str, Any]] = {
            self.node_id: {
                "nodeId": self.node_id,
                "hostName": "localhost",
                "hostname": "localhost",
                "address": "127.0.0.1:5100",
                "ipAddress": "127.0.0.1",
                "port": 5100,
                "state": "Healthy",
                "status": "Healthy",
                "roles": ["Worker", "Host", "Genesis"],
                "capabilities": {"cpu_threads": 8, "ram_mb": 16384},
                "lastHeartbeat": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        }
        self._leases: dict[str, dict[str, Any]] = {}
        self._storage: dict[str, bytes] = {}
        self._events: list[dict[str, Any]] = []

    def __enter__(self) -> EmulatedIpcClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        pass

    def set_config(self, key: str, value: Any) -> None:
        """Set a simulated configuration value."""
        self._config[key] = value

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a simulated configuration value."""
        return self._config.get(key, default)

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
                val = json if json is not None else data
                self._config[key] = val
                return httpx.Response(200, json={"key": key, "value": val}, request=req)

        # 2. Membership endpoints
        if norm_path == "/cell/local-node":
            return httpx.Response(200, json=self._members[self.node_id], request=req)

        if norm_path == "/cell/members":
            return httpx.Response(200, json={"members": list(self._members.values())}, request=req)

        if norm_path == "/cell/members/count":
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

        # 4. Lease endpoints
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

        # 5. Storage endpoints
        if norm_path == "/cell/storage/write":
            p = query.get("path", [""])[0] or (json.get("path") if isinstance(json, dict) else "")
            payload = data or (json.get("content") if isinstance(json, dict) else b"")
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            self._storage[p] = payload
            return httpx.Response(200, json={"written": True, "size": len(payload)}, request=req)

        if norm_path in ("/cell/storage/read", "/cell/storage/range"):
            p = query.get("path", [""])[0]
            content = self._storage.get(p)
            if content is None:
                return httpx.Response(404, text="Not Found", request=req)
            if norm_path == "/cell/storage/range":
                offset = int(query.get("offset", [0])[0])
                count = int(query.get("count", [len(content)])[0])
                slice_bytes = content[offset : offset + count]
                return httpx.Response(200, content=slice_bytes, request=req)
            return httpx.Response(200, content=content, request=req)

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
                    content = self._storage.get(sub)
                    if content is None:
                        return httpx.Response(404, text="Not Found", request=req)
                    return httpx.Response(200, content=content, request=req)
                if method == "DELETE":
                    self._storage.pop(sub, None)
                    return httpx.Response(200, json={"deleted": True}, request=req)

        # 6. Events endpoints
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
        pass

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._route("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._route("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._route("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._route("DELETE", path, **kwargs)
