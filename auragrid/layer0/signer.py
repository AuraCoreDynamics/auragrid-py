from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from .models import SignatureBlock, WasmManifest, WasmPayload


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
        self.public_key = self.private_key.public_key()

    def sign_bytes(self, data: bytes) -> SignatureBlock:
        """Signs raw bytes and returns a SignatureBlock."""
        signature = self.private_key.sign(data)
        public_key_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return SignatureBlock(signature=signature, public_key=public_key_bytes)

    def sign_payload(
        self,
        wasm_bytes: bytes,
        manifest: WasmManifest,
        system_privileged: bool = False,
    ) -> WasmPayload:
        """Signs WASM bytes and manifest to produce a WasmPayload."""
        signature = self.private_key.sign(wasm_bytes)
        return WasmPayload(
            wasmBytes=wasm_bytes,
            signatures=[signature],
            signerIdentities=[self.identity],
            manifest=manifest,
            systemPrivileged=system_privileged,
        )

    def append_signature(self, payload: WasmPayload) -> WasmPayload:
        """Adds this signer's signature to an existing multi-sig payload."""
        signature = self.private_key.sign(payload.wasm_bytes)
        payload.signatures.append(signature)
        payload.signer_identities.append(self.identity)
        return payload
