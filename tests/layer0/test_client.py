import json
import socket
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization

from auragrid.layer0 import (
    Layer0Client,
    WasmManifest,
    WasmPayload,
    WasmSigner,
)


# ────────────────────────────────────────────────────────────────────────────
# WasmSigner.generate_key_pair
# ────────────────────────────────────────────────────────────────────────────


def test_generate_key_pair_returns_valid_hex():
    pub_hex, priv_hex = WasmSigner.generate_key_pair()
    assert len(pub_hex) > 0
    assert len(priv_hex) > 0
    bytes.fromhex(pub_hex)  # should not raise
    bytes.fromhex(priv_hex)


def test_generate_key_pair_public_key_is_spki():
    """Public key must be SubjectPublicKeyInfo DER bytes — as C# Gatekeeper expects."""
    pub_hex, _ = WasmSigner.generate_key_pair()
    pub_bytes = bytes.fromhex(pub_hex)
    # Should load as ECDSA public key (SPKI format)
    key = serialization.load_der_public_key(pub_bytes)
    assert isinstance(key, ec.EllipticCurvePublicKey)
    assert isinstance(key.curve, ec.SECP256R1)


def test_generate_key_pair_private_key_is_pkcs8():
    """Private key must be PKCS#8 DER bytes — required by WasmSigner constructor."""
    _, priv_hex = WasmSigner.generate_key_pair()
    priv_bytes = bytes.fromhex(priv_hex)
    key = serialization.load_der_private_key(priv_bytes, password=None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)


def test_generate_key_pair_produces_unique_keys():
    pub1, priv1 = WasmSigner.generate_key_pair()
    pub2, priv2 = WasmSigner.generate_key_pair()
    assert pub1 != pub2
    assert priv1 != priv2


# ────────────────────────────────────────────────────────────────────────────
# WasmSigner.sign_payload
# ────────────────────────────────────────────────────────────────────────────


def test_wasm_signer_signing():
    """Verify WasmSigner can sign a script and produce a verifiable payload."""
    pub_hex, priv_key_hex = WasmSigner.generate_key_pair()

    signer = WasmSigner(priv_key_hex, identity="test-supervisor")
    script = b"print('hello world')"
    manifest = WasmManifest(timeoutMs=10000)

    payload = signer.sign_payload(script, manifest)

    assert payload.wasm_bytes == script
    assert len(payload.signatures) == 1
    assert payload.signer_identities == ["test-supervisor"]
    assert payload.manifest.timeout_ms == 10000

    # Verify the ECDSA signature against the public key
    public_key = serialization.load_der_public_key(bytes.fromhex(pub_hex))
    public_key.verify(payload.signatures[0], script, ec.ECDSA(hashes.SHA256()))


def test_sign_payload_system_privileged_flag():
    _, priv = WasmSigner.generate_key_pair()
    signer = WasmSigner(priv, "svc-01")
    payload = signer.sign_payload(b"wasm", WasmManifest(), system_privileged=True)
    assert payload.system_privileged is True


def test_sign_payload_default_not_privileged():
    _, priv = WasmSigner.generate_key_pair()
    signer = WasmSigner(priv, "svc-01")
    payload = signer.sign_payload(b"wasm", WasmManifest())
    assert payload.system_privileged is False


# ────────────────────────────────────────────────────────────────────────────
# WasmSigner.sign_bytes (SignatureBlock)
# ────────────────────────────────────────────────────────────────────────────


def test_signature_block_generation():
    """Verify sign_bytes returns a valid SignatureBlock."""
    pub_hex, priv_hex = WasmSigner.generate_key_pair()
    signer = WasmSigner(priv_hex, identity="test-signer")

    data = b"some random data"
    block = signer.sign_bytes(data)

    assert block.signature
    assert block.public_key

    # Public key in block should match the signer's SPKI public key
    expected_pub = bytes.fromhex(pub_hex)
    assert block.public_key == expected_pub

    # Verify signature
    pub_key = serialization.load_der_public_key(block.public_key)
    pub_key.verify(block.signature, data, ec.ECDSA(hashes.SHA256()))


# ────────────────────────────────────────────────────────────────────────────
# WasmSigner.append_signature (multi-sig)
# ────────────────────────────────────────────────────────────────────────────


def test_append_signature_adds_second_sig():
    _, priv1 = WasmSigner.generate_key_pair()
    _, priv2 = WasmSigner.generate_key_pair()
    signer1 = WasmSigner(priv1, "master-1")
    signer2 = WasmSigner(priv2, "master-2")

    wasm = b"emergency payload"
    payload = signer1.sign_payload(wasm, WasmManifest(), system_privileged=True)
    assert len(payload.signatures) == 1

    dual_payload = signer2.append_signature(payload)
    assert len(dual_payload.signatures) == 2
    assert "master-1" in dual_payload.signer_identities
    assert "master-2" in dual_payload.signer_identities


def test_append_signature_does_not_mutate_original():
    _, priv1 = WasmSigner.generate_key_pair()
    _, priv2 = WasmSigner.generate_key_pair()
    s1 = WasmSigner(priv1, "a")
    s2 = WasmSigner(priv2, "b")

    payload = s1.sign_payload(b"data", WasmManifest())
    dual = s2.append_signature(payload)

    # Original must be untouched (append_signature uses model_copy)
    assert len(payload.signatures) == 1
    assert len(dual.signatures) == 2


# ────────────────────────────────────────────────────────────────────────────
# Layer0Client serialization
# ────────────────────────────────────────────────────────────────────────────


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

        assert mock_socket.sendto.called
        args, _ = mock_socket.sendto.call_args
        sent_data = args[0]
        sent_addr = args[1]

        assert sent_addr == ("127.0.0.1", 9999)

        decoded_json = json.loads(sent_data.decode("utf-8"))
        assert decoded_json["wasmBytes"] == "ZmFrZS13YXNt"  # base64 for b"fake-wasm"
        assert decoded_json["signatures"] == ["c2lnMQ=="]  # base64 for b"sig1"
        assert decoded_json["signerIdentities"] == ["signer1"]
        assert decoded_json["manifest"]["timeoutMs"] == 5000


def test_client_uses_configured_host_and_port():
    manifest = WasmManifest()
    payload = WasmPayload(
        wasmBytes=b"data", signatures=[], signerIdentities=[], manifest=manifest
    )
    client = Layer0Client(host="192.168.1.50", port=19000)

    with patch("socket.socket") as mock_socket_class:
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        client.fire_payload(payload)

        _, addr = mock_socket.sendto.call_args[0]
        assert addr == ("192.168.1.50", 19000)


# ────────────────────────────────────────────────────────────────────────────
# Cross-sovereignty: Python key format compatible with C# SPKI expectations
# ────────────────────────────────────────────────────────────────────────────


def test_spki_public_key_round_trips():
    """The public key exported from Python must be re-importable as DER SPKI."""
    pub_hex, priv_hex = WasmSigner.generate_key_pair()

    # Round-trip: hex → bytes → load → re-export → hex
    pub_bytes = bytes.fromhex(pub_hex)
    key = serialization.load_der_public_key(pub_bytes)
    re_exported = key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    assert re_exported == pub_bytes


def test_ecdsa_signature_verifiable_from_exported_public_key():
    """End-to-end: sign with WasmSigner, verify using raw ECDSA public key verification."""
    pub_hex, priv_hex = WasmSigner.generate_key_pair()
    signer = WasmSigner(priv_hex, "cross-sov-test")

    wasm = b"\x00\x61\x73\x6d\x01\x00\x00\x00"  # minimal WASM header
    payload = signer.sign_payload(wasm, WasmManifest())

    pub_key = serialization.load_der_public_key(bytes.fromhex(pub_hex))
    # Should not raise — signature is valid
    pub_key.verify(payload.signatures[0], wasm, ec.ECDSA(hashes.SHA256()))

