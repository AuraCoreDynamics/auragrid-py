"""Tests for stdin-based IPC token loading."""

import os
import sys
from io import StringIO
from unittest.mock import patch


def test_load_tokens_from_stdin_parses_protocol():
    """Verify the stdin protocol parser extracts IPC_TOKEN and FENCING_TOKEN."""
    import auragrid.ipc as ipc_mod

    # Reset module state
    ipc_mod._stdin_tokens_loaded = False
    ipc_mod._stdin_tokens.clear()

    fake_stdin = StringIO("IPC_TOKEN=test-secret-123\nFENCING_TOKEN=42\n---\n")
    with patch.dict(os.environ, {"AURAGRID_IPC_STDIN_ENABLED": "1"}, clear=False), \
         patch.object(sys, "stdin", fake_stdin):
        os.environ.pop("AURAGRID_IPC_TOKEN", None)
        ipc_mod._load_tokens_from_stdin()

    assert ipc_mod._stdin_tokens.get("IPC_TOKEN") == "test-secret-123"
    assert ipc_mod._stdin_tokens.get("FENCING_TOKEN") == "42"


def test_load_tokens_skips_when_not_grid_launched():
    """Verify no stdin read when AURAGRID_IPC_STDIN_ENABLED is not set."""
    import auragrid.ipc as ipc_mod

    ipc_mod._stdin_tokens_loaded = False
    ipc_mod._stdin_tokens.clear()

    fake_stdin = StringIO("IPC_TOKEN=should-not-read\n---\n")
    with patch.dict(os.environ, {}, clear=True), \
         patch.object(sys, "stdin", fake_stdin):
        ipc_mod._load_tokens_from_stdin()

    assert ipc_mod._stdin_tokens.get("IPC_TOKEN") is None


def test_load_tokens_skips_when_mas_id_set_but_stdin_not_enabled():
    """Verify no stdin read when AURAGRID_MAS_ID is set but AURAGRID_IPC_STDIN_ENABLED is not.

    This is the key regression test: operators who set AURAGRID_MAS_ID for local
    testing must not have their terminal blocked by a readline() call.
    """
    import auragrid.ipc as ipc_mod

    ipc_mod._stdin_tokens_loaded = False
    ipc_mod._stdin_tokens.clear()

    fake_stdin = StringIO("IPC_TOKEN=should-not-read\n---\n")
    with patch.dict(os.environ, {"AURAGRID_MAS_ID": "test-mas"}, clear=True), \
         patch.object(sys, "stdin", fake_stdin):
        ipc_mod._load_tokens_from_stdin()

    assert ipc_mod._stdin_tokens.get("IPC_TOKEN") is None
