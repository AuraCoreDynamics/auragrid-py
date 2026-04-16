from __future__ import annotations

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .models import SignatureBlock, WasmManifest, WasmPayload


class WasmSigner:
    """ECDSA P-256 signing utility for Layer 0 WASM-DMZ payloads.

    Keys are stored as SubjectPublicKeyInfo (SPKI) / PKCS#8 DER bytes
    to match the C# ``Layer0Gatekeeper`` wire format.
    Signatures are DER-encoded ECDSA over SHA-256.
    """

    def __init__(self, private_key_hex: str, identity: str):
        """
        Initialize with a hex-encoded PKCS#8 DER ECDSA P-256 private key.

        Args:
            private_key_hex: Hex-encoded PKCS#8 DER private key (produced by
                ``WasmSigner.generate_key_pair()``).
            identity: String identifying the signer (e.g., 'Supervisor-01').
        """
        key_bytes = bytes.fromhex(private_key_hex)
        self.private_key = serialization.load_der_private_key(key_bytes, password=None)
        self.identity = identity
        self.public_key = self.private_key.public_key()

    @staticmethod
    def generate_key_pair() -> tuple[str, str]:
        """Generate a new ECDSA P-256 key pair.

        Returns:
            Tuple of (spki_public_key_hex, pkcs8_private_key_hex).
            Store the public key hex in ``Layer0SecurityOptions.ServicePublicKeys``
            and the private key hex in the signer's secure key store.
        """
        private_key = ec.generate_private_key(ec.SECP256R1())
        pub_hex = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).hex()
        priv_hex = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).hex()
        return pub_hex, priv_hex

    def sign_bytes(self, data: bytes) -> SignatureBlock:
        """Signs raw bytes and returns a SignatureBlock."""
        signature = self.private_key.sign(data, ec.ECDSA(hashes.SHA256()))
        public_key_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return SignatureBlock(signature=signature, public_key=public_key_bytes)

    def sign_payload(
        self,
        wasm_bytes: bytes,
        manifest: WasmManifest,
        system_privileged: bool = False,
    ) -> WasmPayload:
        """Signs WASM bytes and manifest to produce a WasmPayload."""
        signature = self.private_key.sign(wasm_bytes, ec.ECDSA(hashes.SHA256()))
        return WasmPayload(
            wasmBytes=wasm_bytes,
            signatures=[signature],
            signerIdentities=[self.identity],
            manifest=manifest,
            systemPrivileged=system_privileged,
        )

    def append_signature(self, payload: WasmPayload) -> WasmPayload:
        """Adds this signer's signature to an existing multi-sig payload."""
        signature = self.private_key.sign(payload.wasm_bytes, ec.ECDSA(hashes.SHA256()))
        return payload.model_copy(update={
            "signatures": [*payload.signatures, signature],
            "signer_identities": [*payload.signer_identities, self.identity],
        })
