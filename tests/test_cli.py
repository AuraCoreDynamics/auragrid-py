"""Unit tests for AuraGrid Developer CLI tooling."""

import argparse
import json
import os
import tempfile
import zipfile
import pytest

from auragrid.cli import (
    _get_field,
    _handle_init,
    _handle_pack,
    _handle_validate,
    _handle_completion,
)


def test_get_field_case_insensitivity() -> None:
    data = {"AppId": "my-app", "services": [{"MasId": "mas-1"}]}
    assert _get_field(data, "appId") == "my-app"
    assert _get_field(data, "APPID") == "my-app"
    assert _get_field(data, "missing", default="fallback") == "fallback"
    assert _get_field(data, "Services")[0]["MasId"] == "mas-1"


def test_init_scaffolding_python(tmp_path) -> None:
    app_dir = tmp_path / "test-worker"
    args = argparse.Namespace(name=str(app_dir), template="python")
    _handle_init(args)

    assert os.path.exists(app_dir / "app.manifest.json")
    assert os.path.exists(app_dir / "app.py")
    assert os.path.exists(app_dir / "README.md")

    with open(app_dir / "app.manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["appId"] == str(app_dir)
    assert len(manifest["services"]) == 1
    assert manifest["services"][0]["runtime"] == "Python"


def test_pack_bundle(tmp_path) -> None:
    app_dir = tmp_path / "pack-app"
    os.makedirs(app_dir, exist_ok=True)
    manifest = {
        "appId": "pack-app",
        "name": "Pack App",
        "version": "1.0.0",
        "services": [
            {
                "masId": "pack-mas",
                "displayName": "Pack MAS",
                "mode": "Distributed",
                "runtime": "Python",
                "pythonConfig": {"scriptPath": "main.py"}
            }
        ]
    }
    with open(app_dir / "app.manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    with open(app_dir / "main.py", "w", encoding="utf-8") as f:
        f.write("print('hello')\n")

    pkg_path = tmp_path / "pack-app.agp"
    args = argparse.Namespace(directory=str(app_dir), output=str(pkg_path))
    _handle_pack(args)

    assert os.path.exists(pkg_path)
    with zipfile.ZipFile(pkg_path, "r") as z:
        names = z.namelist()
        assert "app.manifest.json" in names
        assert "main.py" in names


def test_validate_valid_directory(tmp_path, capsys) -> None:
    app_dir = tmp_path / "valid-app"
    os.makedirs(app_dir, exist_ok=True)
    manifest = {
        "AppId": "valid-app",
        "Name": "Valid App",
        "Version": "1.0.0",
        "Services": [
            {
                "MasId": "valid-mas",
                "DisplayName": "Valid MAS",
                "Mode": "CellSingleton",
                "Runtime": "Python",
                "PythonConfig": {"ScriptPath": "worker.py"}
            }
        ]
    }
    with open(app_dir / "app.manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    with open(app_dir / "worker.py", "w", encoding="utf-8") as f:
        f.write("# worker\n")

    args = argparse.Namespace(path=str(app_dir))
    _handle_validate(args)

    out = capsys.readouterr().out
    assert "[OK] Application 'valid-app' v1.0.0 manifest is valid!" in out


def test_validate_invalid_manifest(tmp_path) -> None:
    app_dir = tmp_path / "invalid-app"
    os.makedirs(app_dir, exist_ok=True)
    manifest = {
        # Missing appId
        "version": "1.0.0",
        "services": []
    }
    with open(app_dir / "app.manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    args = argparse.Namespace(path=str(app_dir))
    with pytest.raises(SystemExit):
        _handle_validate(args)


def test_completion_output(capsys) -> None:
    args_ps = argparse.Namespace(shell="powershell")
    _handle_completion(args_ps)
    out_ps = capsys.readouterr().out
    assert "Register-ArgumentCompleter" in out_ps
    assert "auragrid" in out_ps

    args_bash = argparse.Namespace(shell="bash")
    _handle_completion(args_bash)
    out_bash = capsys.readouterr().out
    assert "_auragrid_completions" in out_bash


def test_init_scaffolding_auracode_agent(tmp_path) -> None:
    agent_dir = tmp_path / "my-agent"
    args = argparse.Namespace(name=str(agent_dir), template="auracode-agent")
    _handle_init(args)

    assert os.path.exists(agent_dir / "app.manifest.json")
    assert os.path.exists(agent_dir / "agent.py")

    with open(agent_dir / "app.manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["appId"] == str(agent_dir)
    assert manifest["services"][0]["mode"] == "CellSingleton"
    assert manifest["dependencies"][0]["contractId"] == "ai.router.v1"

