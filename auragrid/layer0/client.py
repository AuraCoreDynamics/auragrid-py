from __future__ import annotations

import socket

from .models import WasmPayload


class Layer0Client:
    """Client for shipping WASM-DMZ payloads to the out-of-band Layer 0 port."""

    def __init__(self, host: str = "localhost", port: int = 9000):
        """
        Initialize the Layer 0 client.

        Args:
            host: Target node IP or hostname. Defaults to localhost.
            port: Out-of-band UDP port. Defaults to 9000.
        """
        self.host = host
        self.port = port

    def fire_payload(self, payload: WasmPayload):
        """
        Sends the payload to the Layer 0 daemon via UDP.

        This is an out-of-band, fire-and-forget transmission.

        Args:
            payload: The signed WasmPayload to send.
        """
        # Serialize to JSON with camelCase aliases.
        # Pydantic v2 model_dump_json() handles bytes as base64 automatically.
        data = payload.model_dump_json(by_alias=True).encode("utf-8")

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(data, (self.host, self.port))
