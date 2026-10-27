"""Unit tests for AuraGrid offline standalone emulation mode."""

import os
import pytest
from auragrid import (
    GridContext,
    AsyncGridContext,
    EmulatedIpcClient,
    AsyncEmulatedIpcClient,
)


def test_emulated_ipc_client_sync() -> None:
    client = EmulatedIpcClient()
    
    # 1. Config
    client.set_config("test/key", "my-value")
    resp = client.get("/cell/config/test/key")
    assert resp.status_code == 200
    assert resp.json()["value"] == "my-value"
    
    # 2. Local Node & Members
    resp = client.get("/cell/local-node")
    assert resp.status_code == 200
    assert resp.json()["nodeId"] == "emulated-local-node"
    
    resp = client.get("/cell/members")
    assert resp.status_code == 200
    members = resp.json()["members"]
    assert len(members) >= 1
    assert members[0]["nodeId"] == "emulated-local-node"
    
    # 3. Leases
    resp = client.post("/leases/acquire", json={"resource": "db-write", "ttlSeconds": 30})
    assert resp.status_code == 200
    assert resp.json()["granted"] is True
    
    # 4. Storage
    resp = client.put("/cell/storage/state.txt", content=b"emulated state data")
    assert resp.status_code == 200
    
    resp = client.get("/cell/storage/state.txt")
    assert resp.status_code == 200
    assert resp.content == b"emulated state data"


@pytest.mark.asyncio
async def test_emulated_ipc_client_async() -> None:
    client = AsyncEmulatedIpcClient()
    
    client.set_config("async/key", "async-value")
    resp = await client.get("/cell/config/async/key")
    assert resp.status_code == 200
    assert resp.json()["value"] == "async-value"
    
    resp = await client.get("/cell/local-node")
    assert resp.status_code == 200
    assert resp.json()["nodeId"] == "emulated-local-node"


def test_grid_context_standalone_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AURAGRID_EMULATION_MODE", "1")
    monkeypatch.setenv("AURAGRID_STORAGE_PATH", str(tmp_path))
    
    with GridContext() as ctx:
        assert ctx.is_standalone is True
        
        # Access config
        val = ctx.config.get("filesystem/grid-root")
        assert val == "./.grid-storage"
        
        # Access membership
        members = ctx.membership.get_members()
        assert len(members) >= 1
        assert members[0].node_id == "emulated-local-node"
        
        local = ctx.membership.get_local_node()
        assert local.node_id == "emulated-local-node"
        
        # Access governance
        decision = ctx.governance.can_deploy("my-app", "admin")
        assert decision.is_permitted is True


@pytest.mark.asyncio
async def test_async_grid_context_standalone_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AURAGRID_EMULATION_MODE", "1")
    monkeypatch.setenv("AURAGRID_STORAGE_PATH", str(tmp_path))
    
    async with AsyncGridContext() as ctx:
        assert ctx.is_standalone is True
        
        val = await ctx.config.get("filesystem/grid-root")
        assert val == "./.grid-storage"
        
        members = await ctx.membership.get_members()
        assert len(members) >= 1
        assert members[0].node_id == "emulated-local-node"
