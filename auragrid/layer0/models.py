"""Pydantic models for Layer 0 WASM-DMZ contracts.

These mirror the C# records in ``AuraGrid.Abstractions.Layer0``.
"""

from __future__ import annotations

import base64
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class WasmManifest(BaseModel):
    """Execution capabilities for a WASM script."""

    model_config = ConfigDict(populate_by_name=True)

    allow_network: bool = Field(default=False, alias="allowNetwork")
    allowed_hosts: list[str] = Field(default_factory=list, alias="allowedHosts")
    allowed_paths: list[str] = Field(default_factory=list, alias="allowedPaths")
    timeout_ms: int = Field(default=30000, alias="timeoutMs")
    allow_scratch_write: bool = Field(default=False, alias="allowScratchWrite")


class SignatureBlock(BaseModel):
    """A cryptographic signature and the corresponding public key."""

    model_config = ConfigDict(populate_by_name=True)

    signature: bytes
    public_key: bytes = Field(alias="publicKey")

    @field_serializer("signature", "public_key")
    def serialize_bytes(self, v: bytes, _info):
        return base64.b64encode(v).decode("utf-8")


class WasmPayload(BaseModel):
    """Signed execution payload for Layer 0."""

    model_config = ConfigDict(populate_by_name=True)

    wasm_bytes: bytes = Field(alias="wasmBytes")
    signatures: list[bytes] = Field(default_factory=list)
    signer_identities: list[str] = Field(default_factory=list, alias="signerIdentities")
    manifest: WasmManifest
    system_privileged: bool = Field(default=False, alias="systemPrivileged")

    @field_serializer("wasm_bytes")
    def serialize_wasm_bytes(self, v: bytes, _info):
        return base64.b64encode(v).decode("utf-8")

    @field_serializer("signatures")
    def serialize_signatures(self, v: list[bytes], _info):
        return [base64.b64encode(b).decode("utf-8") for b in v]


class WasmResult(BaseModel):
    """Outcome of a WASM execution."""

    model_config = ConfigDict(populate_by_name=True)

    success: bool
    exit_code: int = Field(alias="exitCode")
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    duration_ms: float = Field(alias="durationMs")
    sandbox_error: Optional[str] = Field(default=None, alias="sandboxError")
