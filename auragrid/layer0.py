import socket
from typing import List, Optional
from cryptography.hazmat.primitives.asymmetric import ed25519
from .models import WasmPayload, WasmManifest, WasmResult

class WasmSigner:
    """Ed25519 signing utility for Layer 0 WASM-DMZ payloads."""

    def __init__(self, private_key_hex: str, identity: str):
        """
        Initialize with a hex-encoded Ed25519 private key.
        
        Args:
            private_key_hex: 64-character hex string (32 bytes).
            identity: String identifying the signer (e.g., 'Supervisor-01').
        """
        self.private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
            bytes.fromhex(private_key_hex)
        )
        self.identity = identity

    def sign_payload(self, wasm_bytes: bytes, manifest: WasmManifest, system_privileged: bool = False) -> WasmPayload:
        """Signs WASM bytes and manifest to produce a WasmPayload."""
        signature = self.private_key.sign(wasm_bytes)
        return WasmPayload(
            wasmBytes=wasm_bytes,
            signatures=[signature],
            signerIdentities=[self.identity],
            manifest=manifest,
            systemPrivileged=system_privileged
        )

    def append_signature(self, payload: WasmPayload) -> WasmPayload:
        """Adds this signer's signature to an existing multi-sig payload."""
        signature = self.private_key.sign(payload.wasm_bytes)
        payload.signatures.append(signature)
        payload.signer_identities.append(self.identity)
        return payload

class Layer0Client:
    """Client for shipping WASM-DMZ payloads to the out-of-band Layer 0 port."""

    def __init__(self, host: str = "localhost", port: int = 9000):
        self.host = host
        self.port = port

    def ship_payload(self, payload: WasmPayload):
        """
        Sends the payload to the Layer 0 daemon via UDP.
        
        Args:
            payload: The signed WasmPayload to send.
        """
        # Serialize to JSON (mirrors the C# daemon's expectation)
        data = payload.model_dump_json(by_alias=True).encode("utf-8")
        
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(data, (self.host, self.port))
