import json
import socket
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from auragrid.layer0 import (
    Layer0Client,
    WasmManifest,
    WasmPayload,
    WasmSigner,
)


def test_wasm_signer_signing():
    """Verify WasmSigner can sign a script and produce a valid payload."""
    # Generate a dummy 32-byte private key
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_key_bytes = private_key.private_bytes_raw()
    private_key_hex = private_key_bytes.hex()

    signer = WasmSigner(private_key_hex, identity="test-supervisor")
    script = b"print('hello world')"
    manifest = WasmManifest(timeoutMs=10000)

    payload = signer.sign_payload(script, manifest)

    assert payload.wasm_bytes == script
    assert len(payload.signatures) == 1
    assert payload.signer_identities == ["test-supervisor"]
    assert payload.manifest.timeout_ms == 10000

    # Verify the signature using the public key
    public_key = private_key.public_key()
    public_key.verify(payload.signatures[0], script)


def test_signature_block_generation():
    """Verify sign_bytes returns a valid SignatureBlock."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_key_hex = private_key.private_bytes_raw().hex()
    signer = WasmSigner(private_key_hex, identity="test-signer")

    data = b"some random data"
    block = signer.sign_bytes(data)

    assert block.signature
    assert block.public_key == private_key.public_key().public_bytes_raw()


def test_client_payload_serialization():
    """Verify Layer0Client serializes payload to JSON with base64 bytes."""
    manifest = WasmManifest(timeoutMs=5000)
    payload = WasmPayload(
        wasmBytes=b"fake-wasm",
        signatures=[b"sig1"],
        signerIdentities=["signer1"],
        manifest=manifest,
    )

    client = Layer0Client(host="127.0.0.1", port=9999)

    with patch("socket.socket") as mock_socket_class:
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket

        client.fire_payload(payload)

        # Check if sendto was called
        assert mock_socket.sendto.called
        args, _ = mock_socket.sendto.call_args
        sent_data = args[0]
        sent_addr = args[1]

        assert sent_addr == ("127.0.0.1", 9999)

        # Verify JSON content
        decoded_json = json.loads(sent_data.decode("utf-8"))
        assert decoded_json["wasmBytes"] == "ZmFrZS13YXNt"  # base64 for b"fake-wasm"
        assert decoded_json["signatures"] == ["c2lnMQ=="]  # base64 for b"sig1"
        assert decoded_json["signerIdentities"] == ["signer1"]
        assert decoded_json["manifest"]["timeoutMs"] == 5000
