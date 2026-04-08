"""Layer 0 WASM-DMZ expansion for AuraGrid.

This package provides tools for signing and transmitting out-of-band
WebAssembly and Python payloads for grid recovery and ephemeral instrumentation.
"""

from .client import Layer0Client
from .models import (
    SignatureBlock,
    WasmManifest,
    WasmPayload,
    WasmResult,
)
from .signer import WasmSigner

__all__ = [
    "Layer0Client",
    "WasmSigner",
    "WasmManifest",
    "WasmPayload",
    "WasmResult",
    "SignatureBlock",
]
