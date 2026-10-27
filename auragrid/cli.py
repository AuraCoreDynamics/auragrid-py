"""CLI entry point for AuraGrid Python SDK.

Usage::

    auragrid doctor
    auragrid status
    auragrid init my-worker --template python
    auragrid validate my-worker
    auragrid pack my-worker -o my-worker.agp
    auragrid dev my-worker
    auragrid apps deploy my-worker.agp
    auragrid apps list
    auragrid apps restart <masId>
    auragrid apps stop <masId>
    auragrid logs [masId]
    auragrid completion powershell
    auragrid generate-descriptor my_module.MyService
    auragrid pki requests
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from typing import Any

import httpx

from .descriptor import save_descriptor

DEFAULT_MGMT_URL = os.environ.get("AURAGRID_URL", "http://localhost:7077")


def _get_client(args: argparse.Namespace) -> httpx.Client:
    """Build an httpx.Client configured with optional mTLS credentials."""
    client_opts: dict[str, Any] = {"verify": False, "timeout": 10.0}
    if hasattr(args, "cert") and args.cert:
        client_opts["cert"] = (args.cert, args.key) if getattr(args, "key", None) else args.cert
    return httpx.Client(**client_opts)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="auragrid",
        description="AuraGrid Developer & Management CLI",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_MGMT_URL,
        help=f"AuraGrid Management API URL (default: {DEFAULT_MGMT_URL})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # doctor command
    subparsers.add_parser("doctor", help="Run local preflight diagnostics on .NET, Python, containers, and node connectivity")

    # status command
    subparsers.add_parser("status", help="Display status and health of the active AuraGrid node")

    # init command
    init_parser = subparsers.add_parser("init", help="Scaffold a new AuraGrid application with manifest, entrypoint, and config")
    init_parser.add_argument("name", nargs="?", default=None, help="Application ID / directory name (omit for interactive wizard)")
    init_parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Launch interactive scaffolding wizard",
    )
    init_parser.add_argument(
        "--template", "-t",
        default="tier1",
        help="App template preset (tier1, tier2, tier3, tier4, tier5, container, csharp, auracode-agent, router-worker)",
    )
    init_parser.add_argument(
        "--runtime", "-r",
        choices=["python", "csharp", "container", "powershell"],
        default="python",
        help="Execution runtime (default: python)",
    )
    init_parser.add_argument(
        "--managed-venv",
        help="AuraSeed managed virtual environment name",
    )
    init_parser.add_argument(
        "--description", "-d",
        help="Application description",
    )

    # run command (standalone / offline emulation mode)
    run_parser = subparsers.add_parser("run", help="Run a Python MAS script or app directory in standalone offline emulation mode")
    run_parser.add_argument("target", nargs="?", default=".", help="Script file (e.g. app.py) or directory containing app.manifest.json")
    run_parser.add_argument("--env-file", default=".env", help="Path to .env file to load (default: .env)")
    run_parser.add_argument("args", nargs="*", help="Arguments forwarded to the script")

    # code command
    code_parser = subparsers.add_parser("code", help="Launch AuraCode assistant connected to the active AuraGrid node")
    code_parser.add_argument("args", nargs="*", help="Arguments forwarded to auracode")

    # validate command
    validate_parser = subparsers.add_parser("validate", help="Validate an application manifest or .agp package before deployment")
    validate_parser.add_argument("path", default=".", nargs="?", help="Application directory with app.manifest.json or .agp bundle file")

    # pack command
    pack_parser = subparsers.add_parser("pack", help="Package an application directory with app.manifest.json into a .agp bundle")
    pack_parser.add_argument("directory", default=".", nargs="?", help="Application directory path (default: current directory)")
    pack_parser.add_argument("--output", "-o", help="Target .agp package file path")
    pack_parser.add_argument("--sign", "-s", help="Path to private key (PEM, DER, or hex) for cryptographic signing")
    pack_parser.add_argument("--force", "-f", action="store_true", help="Force packaging even if pre-flight validation has errors")

    # dev command
    dev_parser = subparsers.add_parser("dev", help="Start live development mode with auto-reload, file watching, and log streaming")
    dev_parser.add_argument("directory", default=".", nargs="?", help="Application directory path (default: current directory)")
    dev_parser.add_argument("--interval", "-i", type=float, default=1.0, help="Polling interval in seconds (default: 1.0)")

    # completion command
    comp_parser = subparsers.add_parser("completion", help="Generate shell auto-completion script for PowerShell or Bash")
    comp_parser.add_argument("shell", choices=["powershell", "bash"], default="powershell", nargs="?", help="Target shell (default: powershell)")

    # apps group
    apps_parser = subparsers.add_parser("apps", help="Manage applications and deployments")
    apps_sub = apps_parser.add_subparsers(dest="apps_command", required=True)

    apps_sub.add_parser("list", help="List registered catalog applications and deployments")

    deploy_parser = apps_sub.add_parser("deploy", help="Deploy an application bundle (.agp) or manifest (.json)")
    deploy_parser.add_argument("path", help="Path to .agp bundle file or app.manifest.json")
    deploy_parser.add_argument("--no-reconcile", action="store_true", help="Register in catalog only without immediate deployment")

    remove_parser = apps_sub.add_parser("remove", help="Remove an application deployment")
    remove_parser.add_argument("app_id", help="App ID to remove")

    restart_parser = apps_sub.add_parser("restart", help="Restart an active MAS instance")
    restart_parser.add_argument("mas_id", help="MAS ID to restart")

    stop_parser = apps_sub.add_parser("stop", help="Stop an active MAS instance")
    stop_parser.add_argument("mas_id", help="MAS ID to stop")

    app_init = apps_sub.add_parser("init", help="Scaffold a new AuraGrid application manifest by tier template")
    app_init.add_argument("name", nargs="?", default=None, help="Application ID / directory name (omit for interactive wizard)")
    app_init.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Launch interactive scaffolding wizard",
    )
    app_init.add_argument(
        "--template", "-t",
        default="tier1",
        help="App template preset (tier1, tier2, tier3, tier4, tier5, container, csharp, auracode-agent, router-worker)",
    )
    app_init.add_argument(
        "--runtime", "-r",
        choices=["python", "csharp", "container", "powershell"],
        default="python",
        help="Execution runtime",
    )
    app_init.add_argument(
        "--managed-venv",
        help="AuraSeed managed virtual environment name",
    )
    app_init.add_argument(
        "--description", "-d",
        help="Application description",
    )

    # logs command
    logs_parser = subparsers.add_parser("logs", help="View and tail live node and MAS logs")
    logs_parser.add_argument("mas_id", nargs="?", help="Optional MAS ID or 'node' (default: all logs)")
    logs_parser.add_argument("--count", "-n", type=int, default=50, help="Number of recent log lines to display (default: 50)")

    # generate-descriptor command
    gen_parser = subparsers.add_parser(
        "generate-descriptor",
        help="Generate a service-descriptor.json from a decorated Python class",
    )
    gen_parser.add_argument(
        "class_path",
        help="Fully qualified class path (e.g., 'my_module.MyService')",
    )
    gen_parser.add_argument(
        "--output",
        "-o",
        default="service-descriptor.json",
        help="Output file path (default: service-descriptor.json)",
    )

    # pki group
    pki_parser = subparsers.add_parser("pki", help="PKI and Certificate management")
    pki_sub = pki_parser.add_subparsers(dest="pki_command", required=True)

    pki_sub.add_parser("requests", help="List pending Certificate Signing Requests (CSRs)")

    app_parser = pki_sub.add_parser("approve", help="Approve and sign a pending CSR")
    app_parser.add_argument("request_id", help="ID of the CSR to sign")
    app_parser.add_argument("--ca-key", required=True, help="Path to CA private key (PFX)")
    app_parser.add_argument("--cert", help="Admin client certificate for mTLS (PEM)")
    app_parser.add_argument("--key", help="Admin client key for mTLS (PEM)")

    gen_root = pki_sub.add_parser("generate-root", help="Originate a brand new Root CA for a fresh grid")
    gen_root.add_argument("--subject", default="CN=AuraGrid-Genesis-CA", help="Subject name for the Root CA")
    gen_root.add_argument("--out", "-o", required=True, help="Output path for the CA private key (PFX)")
    gen_root.add_argument("--force-save", action="store_true", help="Save as Cell CA for auto-approval of bootstrap nodes")
    gen_root.add_argument("--cert", help="Admin client certificate for mTLS (PEM)")
    gen_root.add_argument("--key", help="Admin client key for mTLS (PEM)")

    anchor_parser = pki_sub.add_parser("anchors", help="Manage cell trust anchors")
    anchor_sub = anchor_parser.add_subparsers(dest="anchor_command", required=True)
    add_anc = anchor_sub.add_parser("add", help="Add a new trust anchor (PEM)")
    add_anc.add_argument("path", help="Path to CA certificate PEM file")
    rem_anc = anchor_sub.add_parser("remove", help="Remove a trust anchor by thumbprint")
    rem_anc.add_argument("thumbprint", help="Thumbprint of the CA to remove")

    rev_parser = pki_sub.add_parser("revoke", help="Revoke a node or identity")
    rev_parser.add_argument("id", help="Node ID or Identity to revoke")
    rev_parser.add_argument("--reason", default="Administrative revocation", help="Reason for revocation")

    # service group
    svc_parser = subparsers.add_parser("service", help="Service management and invocation")
    svc_sub = svc_parser.add_subparsers(dest="svc_command", required=True)

    call_parser = svc_sub.add_parser("call", help="Invoke a method on a service")
    call_parser.add_argument("service", help="Service name")
    call_parser.add_argument("method", help="Method name")
    call_parser.add_argument("--data", "-d", help="JSON payload")
    call_parser.add_argument("--cert", help="Client certificate for mTLS (PEM)")
    call_parser.add_argument("--key", help="Client key for mTLS (PEM)")

    args = parser.parse_args()

    if args.command == "doctor":
        _handle_doctor(args)
    elif args.command == "status":
        _handle_status(args)
    elif args.command == "init":
        _handle_init(args)
    elif args.command == "run":
        _handle_run(args)
    elif args.command == "code":
        _handle_code(args)
    elif args.command == "validate":
        _handle_validate(args)
    elif args.command == "pack":
        _handle_pack(args)
    elif args.command == "dev":
        _handle_dev(args)
    elif args.command == "completion":
        _handle_completion(args)
    elif args.command == "apps":
        _handle_apps(args)
    elif args.command == "logs":
        _handle_logs(args)
    elif args.command == "generate-descriptor":
        _generate_descriptor(args.class_path, args.output)
    elif args.command == "pki":
        _handle_pki(args)
    elif args.command == "service":
        _handle_service(args)


def _handle_doctor(args: argparse.Namespace) -> None:
    """Run local preflight diagnostics on .NET, Python, containers, and node connectivity."""
    print("AuraGrid Environment & Diagnostics Doctor")
    print("=" * 60)

    # 1. Python Check
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    print(f"[{'OK' if py_ok else 'WARN'}] Python Version: {py_ver} (>= 3.10 required)")

    # 2. .NET SDK Check
    dotnet_ver = None
    try:
        res = subprocess.run(["dotnet", "--version"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            dotnet_ver = res.stdout.strip()
    except Exception:
        pass
    dotnet_ok = dotnet_ver is not None and dotnet_ver.startswith("10.")
    print(f"[{'OK' if dotnet_ok else 'WARN'}] .NET SDK: {dotnet_ver or 'Not found'} (>= 10.0 recommended)")

    # 3. Container Engine Check
    container_engine = None
    for eng in ["podman", "docker"]:
        try:
            res = subprocess.run([eng, "--version"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                container_engine = f"{eng} ({res.stdout.strip()})"
                break
        except Exception:
            pass
    print(f"[{'OK' if container_engine else 'INFO'}] Container Runtime: {container_engine or 'None detected (optional for Container MAS)'}")

    # 4. Node Connectivity Check
    url = args.url
    node_ok = False
    node_status = None
    with _get_client(args) as client:
        try:
            resp = client.get(f"{url}/api/status")
            if resp.status_code == 200:
                node_ok = True
                node_status = resp.json()
        except Exception:
            # Fallback attempt to alternate port if using default
            if "7077" in url:
                alt_url = url.replace("7077", "7087").replace("http://", "https://")
                try:
                    resp = client.get(f"{alt_url}/api/status")
                    if resp.status_code == 200:
                        node_ok = True
                        url = alt_url
                        node_status = resp.json()
                except Exception:
                    pass

    if node_ok and node_status:
        print(f"[OK] AuraGrid Node: Running at {url} (NodeId: {node_status.get('nodeId')}, Active MAS: {node_status.get('activeMasCount')})")
    else:
        print(f"[INFO] AuraGrid Node: Not responding at {url}. (Launch with 'dotnet run --project src/AuraGrid.Node')")

    # 5. Layer 0 Cache Check
    layer0_paths = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "AuraGrid", "layer0"),
        os.path.expanduser("~/.local/share/AuraGrid/layer0"),
    ]
    layer0_found = any(os.path.exists(p) for p in layer0_paths)
    print(f"[{'OK' if layer0_found else 'INFO'}] Layer 0 Asset Cache: {'Available' if layer0_found else 'Will be fetched automatically on first Node launch'}")
    print("=" * 60)


def _handle_status(args: argparse.Namespace) -> None:
    """Query and display active node status."""
    url = args.url
    with _get_client(args) as client:
        try:
            resp = client.get(f"{url}/api/status")
            if resp.status_code == 200:
                d = resp.json()
                print(f"Node ID:             {d.get('nodeId')}")
                print(f"Active MAS:          {d.get('activeMasCount')}")
                print(f"Registered Services: {d.get('registeredServices')}")
                print(f"Deployments:         {d.get('healthyDeployments')} healthy / {d.get('failedDeployments')} failed")
                print(f"Active Leases:       {d.get('activeLeases')}")
                print(f"Event Topics:        {d.get('eventTopics')}")
            else:
                print(f"Error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Connection failed to {url}: {e}")


def _handle_logs(args: argparse.Namespace) -> None:
    """View and tail live node and MAS logs."""
    url = args.url
    endpoint = f"{url}/api/logs/{args.mas_id}" if args.mas_id else f"{url}/api/logs"
    with _get_client(args) as client:
        try:
            resp = client.get(endpoint)
            if resp.status_code == 200:
                entries = resp.json()
                if not entries:
                    print("No log entries.")
                    return
                for entry in entries[-args.count:]:
                    ts = entry.get("timestamp", "")[:19].replace("T", " ")
                    lvl = entry.get("level", "INFO")
                    node = entry.get("nodeId", "-")
                    msg = entry.get("message", "")
                    exc = entry.get("exception")
                    print(f"[{ts}] [{lvl:<4}] [{node}] {msg}")
                    if exc:
                        print(f"  {exc}")
            else:
                print(f"Error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Failed to fetch logs from {url}: {e}")


def _handle_init(args: argparse.Namespace) -> None:
    """Scaffold a new AuraGrid application manifest by tier template."""
    is_interactive = getattr(args, "interactive", False) or args.name is None

    app_id = args.name
    template = getattr(args, "template", "tier1").lower()
    desc = getattr(args, "description", None)
    runtime = getattr(args, "runtime", "python").capitalize()
    managed_venv = getattr(args, "managed_venv", None) or "aurarouter"

    if is_interactive:
        if not sys.stdin.isatty() and app_id is None:
            print("Error: Application name required when running in non-interactive mode. Usage: auragrid init <name>", file=sys.stderr)
            sys.exit(1)

        print("=" * 65)
        print("         AuraGrid Application Scaffolding Wizard")
        print("=" * 65)
        print("Scaffold a new production-ready AI-native distributed app.\n")

        # 1. Name
        def_name = app_id or "my-worker"
        val = input(f"Application ID / Directory [{def_name}]: ").strip()
        app_id = val or def_name

        # 2. Template
        print("\nAvailable Templates:")
        t_opts = [
            ("tier1", "Tier 1: Sovereign Beacon (Stateless heartbeat & eventing)"),
            ("tier2", "Tier 2: Stateful Gauntlet (SQLite WAL persistence & IPC bridge)"),
            ("tier3", "Tier 3: Sovereign Ledger (Distributed immutable ledger & auditor)"),
            ("tier4", "Tier 4: Cognitive Beacon (LLM-backed inference routing)"),
            ("tier5", "Tier 5: Entropy Engine (Cryptographic consensus & entropy)"),
            ("container", "Container Workload (Alpine / OCI container)"),
            ("auracode-agent", "AuraCode Agent (Autonomous coding agent on AuraGrid)"),
            ("router-worker", "AuraRouter Worker (Model inference worker for router)"),
            ("csharp", "C# MAS (.NET 10 in-process service)"),
        ]
        for idx, (tk, td) in enumerate(t_opts, 1):
            mark = " (default)" if tk == template else ""
            print(f"  {idx}) {td}{mark}")
        sel = input(f"\nSelect template [1-{len(t_opts)}] (default: {template}): ").strip()
        if sel.isdigit() and 1 <= int(sel) <= len(t_opts):
            template = t_opts[int(sel) - 1][0]
        elif sel:
            template = sel.lower()

        # 3. Runtime
        if template == "csharp":
            runtime = "Csharp"
        elif template == "container":
            runtime = "Container"
        else:
            r_val = input(f"Execution runtime (python/csharp/container) [default: {runtime.lower()}]: ").strip().lower()
            if r_val in ("python", "csharp", "container", "powershell"):
                runtime = r_val.capitalize()

        # 4. Managed Venv
        if runtime == "Python":
            mv_val = input(f"AuraSeed managed virtual environment [default: {managed_venv}]: ").strip()
            if mv_val:
                managed_venv = mv_val

        # 5. Description
        desc_val = input("Application description (optional): ").strip()
        if desc_val:
            desc = desc_val
        print()

    target_dir = os.path.abspath(app_id)
    if os.path.exists(target_dir) and os.listdir(target_dir):
        print(f"Error: Directory '{app_id}' already exists and is not empty.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(target_dir, exist_ok=True)
    clean_name = os.path.basename(os.path.normpath(app_id))
    app_name = clean_name.replace("-", " ").replace("_", " ").title()

    manifest: dict[str, Any] = {}

    if template in ("tier1", "tier1-beacon", "tier1-stateless", "python"):
        manifest = {
            "appId": app_id,
            "name": f"Tier 1: {app_name}" if "tier" in template else app_name,
            "version": "1.0.0",
            "description": desc or f"Foundational {runtime} MAS demonstrating sovereign node registration and heartbeat eventing.",
            "services": [
                {
                    "masId": f"{clean_name.lower().replace('_', '-')}-mas",
                    "displayName": f"{app_name} MAS",
                    "mode": "CellSingleton",
                    "runtime": runtime,
                    "pythonConfig": {
                        "scriptPath": "app.py",
                        "workingDirectory": ".",
                        "managedVenvName": managed_venv,
                    } if runtime == "Python" else None,
                    "csharpConfig": {
                        "assemblyPath": f"{clean_name}.dll",
                        "typeName": f"{app_name.replace(' ', '')}.WorkerMas",
                    } if runtime == "Csharp" else None,
                    "remoting": {
                        "enableGrpc": False,
                        "enableOpenApi": True,
                        "enableMcp": True,
                    },
                    "restartPolicy": "OnFailure",
                    "maxRestartAttempts": 3,
                }
            ],
        }
        if runtime != "Python":
            del manifest["services"][0]["pythonConfig"]
        if runtime != "Csharp":
            del manifest["services"][0]["csharpConfig"]

        app_code = f"""import time
import sys

print(f"AuraGrid Tier 1 Beacon started: {{sys.argv[0]}}")
count = 0
while True:
    count += 1
    print(f"[{{time.strftime('%X')}}] Heartbeat tick #{{count}}")
    time.sleep(5)
"""
        with open(os.path.join(target_dir, "app.py"), "w", encoding="utf-8") as f:
            f.write(app_code)

    elif template in ("tier2", "tier2-gauntlet", "tier2-stateful"):
        manifest = {
            "appId": app_id,
            "name": f"Tier 2: {app_name}",
            "version": "1.0.0",
            "description": desc or "Stateful MAS demonstrating resilient local storage, IPC bridge, and fault-tolerance.",
            "services": [
                {
                    "masId": f"{clean_name.lower().replace('_', '-')}-mas",
                    "displayName": f"{app_name} Stateful Worker",
                    "mode": "Distributed",
                    "runtime": "Python",
                    "pythonConfig": {
                        "scriptPath": "stateful_worker.py",
                        "workingDirectory": ".",
                        "managedVenvName": managed_venv,
                    },
                    "remoting": {
                        "enableGrpc": True,
                        "enableOpenApi": True,
                        "enableMcp": True,
                    },
                    "restartPolicy": "OnFailure",
                    "maxRestartAttempts": 5,
                }
            ],
        }
        worker_code = """import os
import sqlite3
import time

DB_PATH = os.environ.get("AURAGRID_STORAGE_PATH", "state.db")
conn = sqlite3.connect(DB_PATH)
conn.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, val INTEGER)")
conn.commit()

print(f"Tier 2 Stateful Worker online with local storage: {DB_PATH}")
count = 0
while True:
    count += 1
    conn.execute("INSERT OR REPLACE INTO state VALUES ('tick', ?)", (count,))
    conn.commit()
    print(f"[{time.strftime('%X')}] Persisted tick #{count}")
    time.sleep(5)
"""
        with open(os.path.join(target_dir, "stateful_worker.py"), "w", encoding="utf-8") as f:
            f.write(worker_code)

    elif template in ("tier3", "tier3-ledger", "tier3-singleton"):
        manifest = {
            "appId": app_id,
            "name": f"Tier 3: {app_name}",
            "version": "1.0.0",
            "description": desc or "Multi-MAS application demonstrating an immutable audit ledger with a separate auditor service.",
            "services": [
                {
                    "masId": f"{clean_name.lower().replace('_', '-')}-ledger-mas",
                    "displayName": "Ledger MAS",
                    "mode": "CellSingleton",
                    "runtime": "Python",
                    "pythonConfig": {
                        "scriptPath": "ledger.py",
                        "workingDirectory": ".",
                        "managedVenvName": managed_venv,
                    },
                    "remoting": {
                        "enableGrpc": True,
                        "enableOpenApi": True,
                        "enableMcp": True,
                    },
                    "restartPolicy": "OnFailure",
                    "maxRestartAttempts": 3,
                },
                {
                    "masId": f"{clean_name.lower().replace('_', '-')}-auditor-mas",
                    "displayName": "Auditor MAS",
                    "mode": "CellSingleton",
                    "runtime": "Python",
                    "pythonConfig": {
                        "scriptPath": "auditor.py",
                        "workingDirectory": ".",
                        "managedVenvName": managed_venv,
                    },
                    "remoting": {
                        "enableGrpc": False,
                        "enableOpenApi": True,
                        "enableMcp": True,
                    },
                    "restartPolicy": "OnFailure",
                    "maxRestartAttempts": 3,
                },
            ],
        }
        ledger_code = """import time

print("Tier 3 Ledger MAS active with WAL resumption.")
while True:
    print(f"[{time.strftime('%X')}] Ledger block committed.")
    time.sleep(5)
"""
        auditor_code = """import time

print("Tier 3 Auditor MAS active.")
while True:
    print(f"[{time.strftime('%X')}] Audit integrity verification OK.")
    time.sleep(10)
"""
        with open(os.path.join(target_dir, "ledger.py"), "w", encoding="utf-8") as f:
            f.write(ledger_code)
        with open(os.path.join(target_dir, "auditor.py"), "w", encoding="utf-8") as f:
            f.write(auditor_code)

    elif template in ("tier4", "tier4-cognitive", "tier4-telemetry"):
        manifest = {
            "appId": app_id,
            "name": f"Tier 4: {app_name}",
            "version": "1.0.0",
            "description": desc or "AI-inference Python MAS demonstrating LLM-backed inference routing through the AuraGrid proxy.",
            "services": [
                {
                    "masId": f"{clean_name.lower().replace('_', '-')}-mas",
                    "displayName": f"{app_name} Cognitive Beacon",
                    "mode": "CellSingleton",
                    "runtime": "Python",
                    "pythonConfig": {
                        "scriptPath": "beacon.py",
                        "workingDirectory": ".",
                        "managedVenvName": managed_venv,
                    },
                    "remoting": {
                        "enableGrpc": True,
                        "enableOpenApi": True,
                        "enableMcp": True,
                    },
                    "restartPolicy": "OnFailure",
                    "maxRestartAttempts": 3,
                }
            ],
            "providesContracts": [
                {
                    "id": f"{clean_name.lower().replace('_', '-')}.inference.v1",
                    "version": "1.0.0",
                }
            ],
            "dependencies": [
                {
                    "contractId": "ai.router.v1",
                    "version": "0.5.5",
                    "preferredImplementationAppId": "aurarouter",
                }
            ],
        }
        beacon_code = """import os
import time

GRID_URL = os.environ.get("AURAGRID_URL", "http://localhost:7077")
print(f"Tier 4 Cognitive Beacon online. Routing via AuraGrid at {GRID_URL}")

while True:
    print(f"[{time.strftime('%X')}] Cognitive beacon heartbeat: ready for inference routing.")
    time.sleep(10)
"""
        with open(os.path.join(target_dir, "beacon.py"), "w", encoding="utf-8") as f:
            f.write(beacon_code)

    elif template in ("tier5", "tier5-consensus", "tier5-entropy"):
        manifest = {
            "appId": app_id,
            "name": f"Tier 5: {app_name}",
            "version": "1.0.0",
            "description": desc or "Python MAS demonstrating sovereign cryptographic entropy generation and WAL-backed audit logging of entropy events.",
            "services": [
                {
                    "masId": f"{clean_name.lower().replace('_', '-')}-mas",
                    "displayName": f"{app_name} Entropy Engine",
                    "mode": "CellSingleton",
                    "runtime": "Python",
                    "pythonConfig": {
                        "scriptPath": "entropy.py",
                        "workingDirectory": ".",
                        "managedVenvName": managed_venv,
                    },
                    "remoting": {
                        "enableGrpc": True,
                        "enableOpenApi": True,
                        "enableMcp": True,
                    },
                    "restartPolicy": "OnFailure",
                    "maxRestartAttempts": 3,
                }
            ],
        }
        entropy_code = """import os
import secrets
import time

print("Tier 5 Sovereign Entropy Engine online.")
while True:
    sample = secrets.token_hex(16)
    print(f"[{time.strftime('%X')}] Cryptographic entropy event: {sample}")
    time.sleep(10)
"""
        with open(os.path.join(target_dir, "entropy.py"), "w", encoding="utf-8") as f:
            f.write(entropy_code)

    elif template == "container":
        manifest = {
            "appId": app_id,
            "name": f"Container: {app_name}",
            "version": "1.0.0",
            "description": desc or f"{app_name} container workload on AuraGrid",
            "services": [
                {
                    "masId": f"{clean_name.lower().replace('_', '-')}-mas",
                    "displayName": f"{app_name} Container",
                    "mode": "Distributed",
                    "runtime": "Container",
                    "containerConfig": {
                        "image": "docker.io/library/alpine:latest",
                        "command": "sleep",
                        "args": ["3600"],
                    },
                    "restartPolicy": "OnFailure",
                    "maxRestartAttempts": 3,
                }
            ],
        }

    elif template == "auracode-agent":
        manifest = {
            "appId": app_id,
            "name": f"AuraCode Agent: {app_name}",
            "version": "1.0.0",
            "description": desc or f"{app_name} autonomous agent on AuraGrid",
            "services": [
                {
                    "masId": f"{clean_name.lower().replace('_', '-')}-mas",
                    "displayName": f"{app_name} Agent",
                    "mode": "CellSingleton",
                    "runtime": "Python",
                    "pythonConfig": {
                        "scriptPath": "agent.py",
                        "arguments": "--loop",
                        "managedVenvName": managed_venv,
                    },
                    "remoting": {
                        "enableGrpc": False,
                        "enableOpenApi": True,
                        "enableMcp": True,
                    },
                    "restartPolicy": "OnFailure",
                    "maxRestartAttempts": 3,
                }
            ],
            "providesContracts": [
                {
                    "id": f"{clean_name.lower().replace('_', '-')}.agent.v1",
                    "version": "1.0.0",
                }
            ],
            "dependencies": [
                {
                    "contractId": "ai.router.v1",
                    "version": "0.5.5",
                    "preferredImplementationAppId": "aurarouter",
                }
            ],
        }
        agent_code = """import os
import time

print("AuraCode Autonomous Agent initialized on AuraGrid.")
while True:
    time.sleep(5)
"""
        with open(os.path.join(target_dir, "agent.py"), "w", encoding="utf-8") as f:
            f.write(agent_code)

    elif template == "router-worker":
        manifest = {
            "appId": app_id,
            "name": f"Router Worker: {app_name}",
            "version": "1.0.0",
            "description": desc or f"{app_name} inference worker for AuraRouter",
            "services": [
                {
                    "masId": f"{clean_name.lower().replace('_', '-')}-worker",
                    "displayName": f"{app_name} Model Worker",
                    "mode": "Distributed",
                    "runtime": "Python",
                    "pythonConfig": {
                        "scriptPath": "worker.py",
                        "managedVenvName": managed_venv,
                    },
                    "remoting": {
                        "enableGrpc": True,
                        "enableOpenApi": True,
                        "enableMcp": True,
                    },
                    "restartPolicy": "OnFailure",
                    "maxRestartAttempts": 3,
                }
            ],
            "providesContracts": [
                {
                    "id": "ai.router.worker.v1",
                    "version": "1.0.0",
                }
            ],
        }
        worker_code = """import time

print("AuraRouter Worker online and registered with local AuraGrid node.")
while True:
    time.sleep(10)
"""
        with open(os.path.join(target_dir, "worker.py"), "w", encoding="utf-8") as f:
            f.write(worker_code)

    else:  # csharp
        manifest = {
            "appId": app_id,
            "name": f"{app_name} Service",
            "version": "1.0.0",
            "description": desc or f"{app_name} in-process C# MAS on AuraGrid",
            "services": [
                {
                    "masId": f"{clean_name.lower().replace('_', '-')}-mas",
                    "displayName": f"{app_name} C# Service",
                    "mode": "Distributed",
                    "runtime": "CSharp",
                    "csharpConfig": {
                        "assemblyPath": f"{clean_name}.dll",
                        "typeName": f"{app_name.replace(' ', '')}.WorkerMas",
                    },
                    "remoting": {
                        "enableGrpc": True,
                        "enableOpenApi": True,
                        "enableMcp": True,
                    },
                    "restartPolicy": "OnFailure",
                    "maxRestartAttempts": 3,
                }
            ],
        }

    manifest_path = os.path.join(target_dir, "app.manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    readme = f"""# {app_name}

AuraGrid Managed Application Service ({template} template).

## Validate Manifest
Ensure manifest adheres strictly to schema:
```bash
auragrid validate .
```

## Build and Package
Package into a distributable `.agp` bundle:
```bash
auragrid pack . -o {clean_name}.agp
```

## Deploy to AuraGrid
Deploy to your local node:
```bash
auragrid apps deploy {clean_name}.agp
```
"""
    with open(os.path.join(target_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)

    print(f"[OK] Created new AuraGrid application '{app_id}' ({template} template) at {target_dir}")
    print(f"[OK] Generated valid app.manifest.json ({len(manifest.get('services', []))} services, remoting enabled)")


def _handle_code(args: argparse.Namespace) -> None:
    """Launch AuraCode assistant or REPL connected to the active AuraGrid node."""
    env = os.environ.copy()
    env["AURAGRID_URL"] = args.url
    env["AURAGRID_ENDPOINT"] = args.url
    env["AURACODE_ROUTING_BACKEND"] = "grid"

    router_url = os.environ.get("AURAROUTER_URL")
    if not router_url:
        router_url = "http://127.0.0.1:8321"
        try:
            with _get_client(args) as client:
                resp = client.get(f"{args.url}/api/services")
                if resp.status_code == 200:
                    services = resp.json()
                    for svc in services:
                        svc_id = svc.get("serviceId", "").lower()
                        contract = svc.get("contractId", "")
                        if "router" in svc_id or contract == "ai.router.v1":
                            endpoints = svc.get("endpoints", [])
                            if endpoints:
                                router_url = endpoints[0]
                                break
        except Exception:
            pass
    env["AURAROUTER_URL"] = router_url

    cmd = [sys.executable, "-m", "auracode"] + (args.args or [])
    print(f"Connecting to AuraGrid at {args.url} (AuraRouter: {router_url}) via AuraCode...")
    try:
        subprocess.run(cmd, env=env)
    except FileNotFoundError:
        print("Error: 'auracode' module not found in the current Python environment.", file=sys.stderr)
        print("Install it with: pip install -e ../auracode", file=sys.stderr)
        sys.exit(1)


def load_env_file(path: str = ".env") -> dict[str, str]:
    """Parse a .env file and inject into os.environ if not already set."""
    env_vars: dict[str, str] = {}
    if not os.path.exists(path):
        return env_vars
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip()
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    env_vars[key] = val
                    if key not in os.environ:
                        os.environ[key] = val
    except Exception as e:
        print(f"[WARN] Failed to load {path}: {e}")
    return env_vars


def resolve_env_vars(val: Any) -> Any:
    """Recursively expand ${env:NAME:-default} or ${NAME} in string, list, or dict."""
    if isinstance(val, str):
        def repl(match: re.Match) -> str:
            expr = match.group(1).strip()
            if expr.startswith("env:"):
                expr = expr[4:]
            var_name, sep, default_val = expr.partition(":-")
            if not sep:
                var_name, sep, default_val = expr.partition(":")
            return os.environ.get(var_name.strip(), default_val if sep else match.group(0))

        return re.sub(r"\$\{([^}]+)\}", repl, val)
    elif isinstance(val, dict):
        return {k: resolve_env_vars(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [resolve_env_vars(item) for item in val]
    return val


def _sign_checksums(checksums_bytes: bytes, key_path: str) -> bytes:
    """Sign checksums.sha256 bytes with an RSA or ECDSA private key."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa, ec, ed25519, utils

    with open(key_path, "rb") as f:
        raw_key = f.read()

    private_key = None
    # 1. Try PEM
    try:
        private_key = serialization.load_pem_private_key(raw_key, password=None)
    except Exception:
        pass

    # 2. Try Hex-encoded DER
    if private_key is None:
        try:
            text = raw_key.decode("utf-8").strip()
            der_bytes = bytes.fromhex(text)
            private_key = serialization.load_der_private_key(der_bytes, password=None)
        except Exception:
            pass

    # 3. Try raw DER
    if private_key is None:
        try:
            private_key = serialization.load_der_private_key(raw_key, password=None)
        except Exception:
            pass

    if private_key is None:
        raise ValueError(f"Unsupported private key format in '{key_path}'. Expected PEM, DER, or hex PKCS#8/PKCS#1.")

    if isinstance(private_key, rsa.RSAPrivateKey):
        return private_key.sign(
            checksums_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
    elif isinstance(private_key, ec.EllipticCurvePrivateKey):
        asn1_sig = private_key.sign(checksums_bytes, ec.ECDSA(hashes.SHA256()))
        r, s = utils.decode_dss_signature(asn1_sig)
        byte_len = (private_key.curve.key_size + 7) // 8
        return r.to_bytes(byte_len, "big") + s.to_bytes(byte_len, "big")
    elif isinstance(private_key, ed25519.Ed25519PrivateKey):
        return private_key.sign(checksums_bytes)
    else:
        raise ValueError(f"Unsupported key type: {type(private_key).__name__}")


def build_agp_package(
    src_dir: str,
    output_path: str,
    sign_key_path: str | None = None,
) -> tuple[int, int]:
    """Package an application folder into a .agp bundle with SHA-256 checksums and secret exclusion.

    Returns:
        tuple[int, int]: (files_packaged_count, sensitive_files_excluded_count)
    """
    sensitive_patterns = [
        re.compile(r"^\.env(\..+)?$", re.IGNORECASE),
        re.compile(r"^.*\.(pem|pfx|key|cer|crt)$", re.IGNORECASE),
        re.compile(r"^.*(credentials|secret|token).*\.json$", re.IGNORECASE),
        re.compile(r"^.*\.(agp|zip|tar|gz|bak)$", re.IGNORECASE),
        re.compile(r"^(\.git|\.github|\.vscode|\.idea|\.pytest_cache|__pycache__|bin|obj)(\/|\\|$)", re.IGNORECASE),
        re.compile(r"^.*\.(pyc|pyo|tmp)$", re.IGNORECASE),
    ]

    def is_sensitive(relpath: str) -> bool:
        normalized = relpath.replace("\\", "/")
        parts = normalized.split("/")
        if any(p in (".git", "__pycache__", "bin", "obj", ".vscode", ".idea", ".pytest_cache") for p in parts):
            return True
        filename = parts[-1]
        for pat in sensitive_patterns:
            if pat.search(filename) or pat.search(normalized):
                return True
        return False

    files_to_pack: list[tuple[str, str]] = []
    checksums: dict[str, str] = {}
    excluded_count = 0

    for root, _, files in os.walk(src_dir):
        for file in files:
            full_path = os.path.join(root, file)
            relpath = os.path.relpath(full_path, src_dir).replace("\\", "/")

            if relpath in ("checksums.sha256", "signature.sig", "sbom.cdx.json"):
                continue

            if is_sensitive(relpath):
                print(f"[SECURITY] Excluded sensitive file from package bundle: {relpath}")
                excluded_count += 1
                continue

            with open(full_path, "rb") as f:
                data = f.read()
            file_hash = hashlib.sha256(data).hexdigest().lower()
            checksums[relpath] = file_hash
            files_to_pack.append((full_path, relpath))

    # Format checksums: lines of <hash>  <relpath>\n, sorted by relpath
    sorted_paths = sorted(checksums.keys())
    checksums_content = "".join(f"{checksums[p]}  {p}\n" for p in sorted_paths)
    checksums_bytes = checksums_content.encode("utf-8")

    signature_bytes: bytes | None = None
    if sign_key_path:
        sign_key_full = os.path.abspath(sign_key_path)
        if not os.path.exists(sign_key_full):
            raise FileNotFoundError(f"Signing key file not found: {sign_key_full}")
        signature_bytes = _sign_checksums(checksums_bytes, sign_key_full)

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for full_path, relpath in files_to_pack:
            zipf.write(full_path, relpath)

        # Embed checksums.sha256 (matches AgpPackageFormat.ChecksumsFileName)
        zipf.writestr("checksums.sha256", checksums_bytes)

        # Embed signature.sig if signed (matches AgpPackageFormat.SignatureFileName)
        if signature_bytes:
            zipf.writestr("signature.sig", signature_bytes)

    return len(files_to_pack), excluded_count


def _get_field(data: dict[str, Any] | None, *keys: str, default: Any = None) -> Any:
    """Retrieve a value from a dictionary trying multiple case-insensitive key names."""
    if not isinstance(data, dict):
        return default
    for k in keys:
        if k in data:
            return data[k]
    lower_map = {k.lower(): v for k, v in data.items()}
    for k in keys:
        if k.lower() in lower_map:
            return lower_map[k.lower()]
    return default


def _validate_target(target: str) -> tuple[bool, list[str], list[str], dict[str, Any] | None]:
    """Validate an application manifest or .agp package before deployment.

    Returns:
        tuple[bool, list[str], list[str], dict[str, Any] | None]:
            (is_valid, errors, warnings, manifest_data)
    """
    errors: list[str] = []
    warnings: list[str] = []
    manifest_data: dict[str, Any] | None = None
    is_archive = target.endswith((".agp", ".zip"))
    archive = None

    if is_archive:
        try:
            archive = zipfile.ZipFile(target, "r")
            namelist = archive.namelist()
            if "app.manifest.json" not in namelist:
                errors.append("Missing app.manifest.json in package root")
                return False, errors, warnings, None
            manifest_content = archive.read("app.manifest.json").decode("utf-8")
            manifest_data = json.loads(manifest_content)

            # Check checksums.sha256
            if "checksums.sha256" not in namelist:
                warnings.append("Missing 'checksums.sha256' manifest in package root (required for secure node deployments)")
            else:
                cs_lines = archive.read("checksums.sha256").decode("utf-8").splitlines()
                for line in cs_lines:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("  ", 1)
                    if len(parts) == 2:
                        h, p = parts
                        if p in namelist:
                            actual_h = hashlib.sha256(archive.read(p)).hexdigest().lower()
                            if actual_h != h.lower():
                                errors.append(f"Checksum mismatch for '{p}': expected {h}, got {actual_h}")
                        else:
                            errors.append(f"File listed in checksums not found in archive: '{p}'")
        except Exception as e:
            errors.append(f"Unable to read package archive: {e}")
            return False, errors, warnings, None
        finally:
            if archive:
                archive.close()
    elif os.path.isdir(target):
        manifest_path = os.path.join(target, "app.manifest.json")
        if not os.path.exists(manifest_path):
            errors.append(f"app.manifest.json not found in directory: {target}")
            return False, errors, warnings, None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except Exception as e:
            errors.append(f"Failed to parse app.manifest.json: {e}")
            return False, errors, warnings, None

        # Check for sensitive files in directory
        for root, _, files in os.walk(target):
            for file in files:
                rel = os.path.relpath(os.path.join(root, file), target).replace("\\", "/")
                if rel.startswith((".git", "__pycache__", "bin", "obj", ".vscode", ".idea")):
                    continue
                if file.startswith(".env") or file.endswith((".pem", ".pfx", ".key", ".cer", ".crt")):
                    warnings.append(f"Detected sensitive credential file '{rel}'. Note: It will be excluded automatically from .agp packages.")
    elif os.path.isfile(target) and target.endswith(".json"):
        try:
            with open(target, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except Exception as e:
            errors.append(f"Failed to parse manifest JSON: {e}")
            return False, errors, warnings, None
    else:
        errors.append(f"Unsupported target '{target}'. Provide a directory or .agp file.")
        return False, errors, warnings, None

    if not isinstance(manifest_data, dict):
        errors.append("Manifest root must be a JSON object")
        return False, errors, warnings, None

    # Check root fields
    app_id = _get_field(manifest_data, "appId")
    if not app_id or not isinstance(app_id, str):
        errors.append("Missing or invalid 'appId' (must be a non-empty string)")
    elif not re.match(r"^[a-zA-Z0-9_\-\.]+$", app_id):
        errors.append(f"Invalid 'appId' format '{app_id}'. Only alphanumeric, '.', '_', '-' allowed.")

    version = _get_field(manifest_data, "version")
    if not version or not isinstance(version, str):
        errors.append("Missing or invalid 'version' (must be semver e.g. 1.0.0)")

    name = _get_field(manifest_data, "name")
    if not name or not isinstance(name, str):
        warnings.append("Missing recommended 'name' display title")

    services = _get_field(manifest_data, "services", default=[])
    if not isinstance(services, list) or len(services) == 0:
        errors.append("At least one service definition is required under 'services'")
    else:
        valid_runtimes = {"python", "dotnet", "csharp", "container", "powershell", "node", "native"}
        valid_modes = {"singleton", "cellsingleton", "distributed", "drafter", "verifier", "replicated", "host", "daemon"}
        seen_mas_ids = set()

        for idx, svc in enumerate(services):
            mas_id = _get_field(svc, "masId")
            if not mas_id:
                errors.append(f"Service #{idx+1} missing required 'masId'")
            elif mas_id in seen_mas_ids:
                errors.append(f"Duplicate masId '{mas_id}' detected in services list")
            else:
                seen_mas_ids.add(mas_id)

            runtime = (_get_field(svc, "runtime") or "").lower()
            if runtime not in valid_runtimes:
                errors.append(f"Service '{mas_id or idx}' has invalid runtime '{_get_field(svc, 'runtime')}'. Must be one of {valid_runtimes}")

            mode = (_get_field(svc, "mode") or "").lower()
            if mode not in valid_modes:
                warnings.append(f"Service '{mas_id or idx}' has unrecognized mode '{_get_field(svc, 'mode')}'. Expected one of {valid_modes}")

            # Validate entrypoints & secrets
            if runtime == "python":
                py_cfg = _get_field(svc, "pythonConfig", default={})
                script = _get_field(py_cfg, "scriptPath")
                if not script:
                    errors.append(f"Python service '{mas_id}' missing 'pythonConfig.scriptPath'")
                elif not is_archive and os.path.isdir(target) and not os.path.exists(os.path.join(target, script)):
                    warnings.append(f"Python script '{script}' not found at {os.path.join(target, script)}")

                # Check environment variables
                env_map = _get_field(py_cfg, "environment", default={})
                if isinstance(env_map, dict):
                    for k, v in env_map.items():
                        if isinstance(v, str) and re.search(r"^(sk-[a-zA-Z0-9_\-]{20,}|ghp_[a-zA-Z0-9]{20,})", v):
                            warnings.append(f"Service '{mas_id}' environment variable '{k}' appears to contain a hardcoded token. Use '${{env:{k}}}' instead.")
            elif runtime in ("csharp", "dotnet"):
                cs_cfg = _get_field(svc, "csharpConfig", default={})
                asm = _get_field(cs_cfg, "assemblyPath")
                if not asm:
                    errors.append(f"C# service '{mas_id}' missing 'csharpConfig.assemblyPath'")
            elif runtime == "container":
                cnt_cfg = _get_field(svc, "containerConfig", default={})
                image = _get_field(cnt_cfg, "image")
                if not image:
                    errors.append(f"Container service '{mas_id}' missing 'containerConfig.image'")

    return len(errors) == 0, errors, warnings, manifest_data


def _handle_pack(args: argparse.Namespace) -> None:
    """Package an application folder into a secure .agp bundle."""
    src_dir = os.path.abspath(args.directory)
    manifest_path = os.path.join(src_dir, "app.manifest.json")
    if not os.path.exists(manifest_path):
        print(f"Error: app.manifest.json not found in {src_dir}", file=sys.stderr)
        sys.exit(1)

    # 1. Pre-flight validation
    force = getattr(args, "force", False)
    is_valid, errors, warnings, manifest = _validate_target(src_dir)
    if not is_valid and not force:
        print("Pre-flight validation failed. Cannot package application bundle:", file=sys.stderr)
        for err in errors:
            print(f"  [FAIL] {err}", file=sys.stderr)
        print("\nFix the errors above or run with --force to override.", file=sys.stderr)
        sys.exit(1)

    app_id = _get_field(manifest, "appId", default="app")
    version = _get_field(manifest, "version", default="1.0.0")
    output = args.output or f"{app_id}-{version}.agp"
    sign_key = getattr(args, "sign", None)

    try:
        packed_count, excluded_count = build_agp_package(src_dir, output, sign_key)
    except Exception as e:
        print(f"Error packaging bundle: {e}", file=sys.stderr)
        sys.exit(1)

    size_kb = os.path.getsize(output) / 1024.0
    print(f"[OK] Successfully packaged '{app_id}' v{version} into '{output}' ({size_kb:.1f} KB, {packed_count} files)")
    print(f"[OK] Embedded root 'checksums.sha256' manifest ({packed_count} entries)")
    if sign_key:
        print(f"[OK] Embedded root 'signature.sig' cryptographic signature ({os.path.basename(sign_key)})")
    if excluded_count > 0:
        print(f"[SECURITY] Excluded {excluded_count} sensitive/build file(s) from distribution bundle")


def _handle_validate(args: argparse.Namespace) -> None:
    """Validate an application manifest or .agp package before deployment."""
    target = os.path.abspath(args.path)
    if not os.path.exists(target):
        print(f"Error: Target path does not exist: {target}", file=sys.stderr)
        sys.exit(1)

    print(f"AuraGrid Application Pre-Flight Validator")
    print("=" * 65)
    print(f"Target: {target}")

    is_valid, errors, warnings, manifest_data = _validate_target(target)

    for err in errors:
        print(f"[FAIL] {err}")
    for warn in warnings:
        print(f"[WARN] {warn}")

    print("=" * 65)
    app_id = _get_field(manifest_data, "appId", default="unknown")
    version = _get_field(manifest_data, "version", default="0.0.0")
    if is_valid:
        print(f"[OK] Application '{app_id}' v{version} manifest is valid!")
        if not warnings:
            print("[OK] All entrypoints, service declarations, and properties passed validation.")
        print("Application is ready to pack or deploy to AuraGrid.")
    else:
        print(f"\nValidation failed with {len(errors)} error(s). Please correct the issues above.", file=sys.stderr)
        sys.exit(1)


def _handle_run(args: argparse.Namespace) -> None:
    """Run a Python MAS script or app directory in standalone offline emulation mode."""
    target = os.path.abspath(args.target)
    script_path = None
    work_dir = None
    manifest_env: dict[str, Any] = {}

    if os.path.isdir(target):
        manifest_path = os.path.join(target, "app.manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                services = _get_field(manifest, "services", default=[])
                if services:
                    py_cfg = _get_field(services[0], "pythonConfig", default={})
                    rel_script = _get_field(py_cfg, "scriptPath")
                    if rel_script:
                        script_path = os.path.join(target, rel_script)
                        work_dir = os.path.join(target, _get_field(py_cfg, "workingDirectory", default="."))
                    manifest_env = _get_field(py_cfg, "environment", default={})
            except Exception as e:
                print(f"Error reading manifest in {target}: {e}", file=sys.stderr)
                sys.exit(1)
        if not script_path:
            for cand in ["app.py", "main.py", "worker.py", "beacon.py"]:
                p = os.path.join(target, cand)
                if os.path.exists(p):
                    script_path = p
                    work_dir = target
                    break
    elif os.path.isfile(target):
        script_path = target
        work_dir = os.path.dirname(target)
    else:
        print(f"Error: Target '{target}' not found.", file=sys.stderr)
        sys.exit(1)

    if not script_path or not os.path.exists(script_path):
        print(f"Error: Could not determine Python script entrypoint in '{target}'.", file=sys.stderr)
        sys.exit(1)

    env_file = getattr(args, "env_file", ".env")
    env_path = os.path.join(work_dir or os.getcwd(), env_file) if not os.path.isabs(env_file) else env_file
    loaded_env = load_env_file(env_path)

    env = os.environ.copy()
    env["AURAGRID_EMULATION_MODE"] = "1"
    env["AURAGRID_STORAGE_PATH"] = env.get(
        "AURAGRID_STORAGE_PATH",
        os.path.join(work_dir or os.getcwd(), "emulated_storage"),
    )

    resolved_manifest_env = resolve_env_vars(manifest_env)
    if isinstance(resolved_manifest_env, dict):
        for k, v in resolved_manifest_env.items():
            env[str(k)] = str(v)

    print("=" * 65)
    print("      AuraGrid Standalone / Offline Emulation Runner")
    print("=" * 65)
    print(f"  Entrypoint:  {script_path}")
    print(f"  Directory:   {work_dir or os.getcwd()}")
    print(f"  Emulation:   AURAGRID_EMULATION_MODE=1 (in-memory cell, zero daemon)")
    if loaded_env:
        print(f"  Environment: Loaded {len(loaded_env)} variables from {env_file}")
    if resolved_manifest_env:
        print(f"  Manifest:    Injected {len(resolved_manifest_env)} service environment variables")
    print("=" * 65)
    print(f"[RUN] Starting process: {sys.executable} {os.path.basename(script_path)}...\n")

    cmd = [sys.executable, script_path] + (args.args or [])
    try:
        proc = subprocess.run(cmd, cwd=work_dir, env=env)
        sys.exit(proc.returncode)
    except KeyboardInterrupt:
        print("\n[INFO] Emulation runner stopped by user.")


def _handle_dev(args: argparse.Namespace) -> None:
    """Start live development mode with auto-reload, file watching, and log streaming."""
    target_dir = os.path.abspath(args.directory)
    manifest_path = os.path.join(target_dir, "app.manifest.json")
    if not os.path.exists(manifest_path):
        print(f"Error: app.manifest.json not found in {target_dir}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"Error reading manifest: {e}", file=sys.stderr)
        sys.exit(1)

    app_id = _get_field(manifest, "appId", default="dev-app")
    version = _get_field(manifest, "version", default="1.0.0")
    services = _get_field(manifest, "services", default=[])
    mas_ids = [_get_field(s, "masId") for s in services if _get_field(s, "masId")]
    primary_mas = mas_ids[0] if mas_ids else app_id
    url = args.url

    print("=" * 65)
    print("           AuraGrid Live Developer Environment")
    print("=" * 65)
    print(f"  App ID:     {app_id} (v{version})")
    print(f"  Directory:  {target_dir}")
    print(f"  Target URL: {url}")
    print(f"  MAS ID(s):  {', '.join(mas_ids) if mas_ids else '-'}")
    print("=" * 65)

    def scan_files() -> dict[str, float]:
        mtimes: dict[str, float] = {}
        for root, _, files in os.walk(target_dir):
            for file in files:
                rel = os.path.relpath(os.path.join(root, file), target_dir)
                if (
                    rel.endswith((".agp", ".tmp", ".pyc", ".git"))
                    or "__pycache__" in rel
                    or "bin" in rel.split(os.sep)
                    or "obj" in rel.split(os.sep)
                ):
                    continue
                full_path = os.path.join(root, file)
                try:
                    mtimes[rel] = os.path.getmtime(full_path)
                except OSError:
                    pass
        return mtimes

    def pack_and_upload(client: httpx.Client) -> bool:
        fd, temp_pkg = tempfile.mkstemp(suffix=".agp")
        os.close(fd)
        try:
            build_agp_package(target_dir, temp_pkg)
            with open(temp_pkg, "rb") as f:
                resp = client.post(
                    f"{url}/api/catalog/upload",
                    headers={
                        "Content-Type": "application/octet-stream",
                        "X-Deploy-Immediately": "true",
                    },
                    content=f.read(),
                )
            if resp.status_code < 300:
                return True
            else:
                print(f"[Deploy Error {resp.status_code}]: {resp.text}")
                return False
        except Exception as e:
            print(f"[Deploy Exception]: {e}")
            return False
        finally:
            if os.path.exists(temp_pkg):
                try:
                    os.remove(temp_pkg)
                except OSError:
                    pass

    seen_log_timestamps: set[str] = set()

    def tail_logs(client: httpx.Client) -> None:
        try:
            log_url = f"{url}/api/logs/{primary_mas}" if primary_mas else f"{url}/api/logs"
            resp = client.get(log_url)
            if resp.status_code == 200:
                logs = resp.json() or []
                for entry in logs[-15:]:
                    ts = entry.get("timestamp", "")
                    key = f"{ts}-{entry.get('message', '')}"
                    if key not in seen_log_timestamps:
                        seen_log_timestamps.add(key)
                        level = entry.get("level", "Info")
                        msg = entry.get("message", "")
                        print(f"[{ts[11:19] if len(ts) >= 19 else ts}] [{level}] {msg}")
        except Exception:
            pass

    with _get_client(args) as client:
        print("--> Performing initial deploy to grid...")
        if pack_and_upload(client):
            print(f"[OK] Application '{app_id}' deployed.")
        else:
            print("[WARN] Initial deployment had issues, watching for file updates to retry...")

        last_files = scan_files()
        print(f"\n[AuraGrid Dev] Watching {len(last_files)} files. (Press Ctrl+C to stop)")
        tail_logs(client)

        try:
            while True:
                time.sleep(args.interval)
                current_files = scan_files()
                changed = []
                for f_rel, mtime in current_files.items():
                    if f_rel not in last_files or last_files[f_rel] != mtime:
                        changed.append(f_rel)
                for f_rel in last_files:
                    if f_rel not in current_files:
                        changed.append(f"{f_rel} (deleted)")

                if changed:
                    time.sleep(0.3)  # Debounce rapid filesystem events
                    current_files = scan_files()
                    last_files = current_files
                    print(f"\n--> [{time.strftime('%X')}] Change detected: {', '.join(changed[:3])}{'...' if len(changed) > 3 else ''}")
                    print("--> Hot-reloading application bundle...")
                    if pack_and_upload(client):
                        # Also attempt fast MAS restart if instance is already alive
                        for m_id in mas_ids:
                            try:
                                client.post(f"{url}/api/mas/{m_id}/restart")
                            except Exception:
                                pass
                        print(f"[OK] Hot-reload complete for '{app_id}'.")
                    time.sleep(0.5)
                    tail_logs(client)
                else:
                    tail_logs(client)

        except KeyboardInterrupt:
            print("\nExiting AuraGrid dev mode.")


def _handle_completion(args: argparse.Namespace) -> None:
    """Generate shell tab-completion script for PowerShell or Bash."""
    shell = args.shell.lower()
    if shell == "powershell":
        script = """# AuraGrid PowerShell Completion Script
# Add to your $PROFILE:
#   Invoke-Expression (& auragrid completion powershell | Out-String)

Register-ArgumentCompleter -Native -CommandName auragrid -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)

    $commands = @(
        "doctor", "status", "init", "code", "validate", "pack", "dev",
        "apps", "logs", "generate-descriptor", "pki", "service", "completion"
    )
    $appsCommands = @("list", "deploy", "remove", "restart", "stop")
    $pkiCommands = @("requests", "approve", "generate-root", "anchors", "revoke")
    $svcCommands = @("call")

    $elements = $commandAst.ToString().Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)

    if ($elements.Count -le 1 -or ($elements.Count -eq 2 -and $wordToComplete)) {
        $commands | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
        }
    } elseif ($elements[1] -eq "apps") {
        $appsCommands | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
        }
    } elseif ($elements[1] -eq "pki") {
        $pkiCommands | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
        }
    } elseif ($elements[1] -eq "service") {
        $svcCommands | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
        }
    }
}
"""
        print(script)
    else:  # bash
        script = """# AuraGrid Bash Completion Script
# Source with: eval "$(auragrid completion bash)"

_auragrid_completions() {
    local cur prev words cword
    _init_completion || return

    local top_commands="doctor status init code validate pack dev apps logs generate-descriptor pki service completion"
    local apps_commands="list deploy remove restart stop"
    local pki_commands="requests approve generate-root anchors revoke"

    if [ "$cword" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$top_commands" -- "$cur") )
        return 0
    fi

    case "${words[1]}" in
        apps)
            if [ "$cword" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "$apps_commands" -- "$cur") )
                return 0
            fi
            ;;
        pki)
            if [ "$cword" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "$pki_commands" -- "$cur") )
                return 0
            fi
            ;;
    esac
}
complete -F _auragrid_completions auragrid
"""
        print(script)



def _handle_apps(args: argparse.Namespace) -> None:
    """Manage applications and deployments."""
    if args.apps_command == "init":
        _handle_init(args)
        return

    url = getattr(args, "url", "https://localhost:7087")
    with _get_client(args) as client:
        if args.apps_command == "list":
            deployments = client.get(f"{url}/api/deployments").json() or []
            catalog = client.get(f"{url}/api/catalog").json() or []
            print(f"{'APP ID':<30} {'VERSION':<10} {'STATUS':<15} {'NAME'}")
            print("-" * 75)
            for d in deployments:
                cat_match = next((c for c in catalog if c.get("appId") == d.get("appId")), {})
                name = cat_match.get("name", "-")
                print(f"{d.get('appId'):<30} {d.get('version'):<10} {d.get('status'):<15} {name}")

        elif args.apps_command == "deploy":
            path = os.path.abspath(args.path)
            if not os.path.exists(path):
                print(f"Error: File not found: {path}", file=sys.stderr)
                sys.exit(1)

            deploy_now = not args.no_reconcile
            if path.endswith((".agp", ".zip")):
                with open(path, "rb") as f:
                    resp = client.post(
                        f"{url}/api/catalog/upload",
                        headers={
                            "Content-Type": "application/octet-stream",
                            "X-Deploy-Immediately": "true" if deploy_now else "false",
                        },
                        content=f.read(),
                    )
            else:
                with open(path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                resp = client.post(
                    f"{url}/api/catalog",
                    json={"manifest": manifest, "deployImmediately": deploy_now},
                )

            if resp.status_code < 300:
                print(f"Application deployed successfully: {resp.text}")
            else:
                print(f"Deploy error ({resp.status_code}): {resp.text}")

        elif args.apps_command == "remove":
            resp = client.delete(f"{url}/api/deployments/{args.app_id}")
            if resp.status_code < 300:
                print(f"Deployment removed: {args.app_id}")
            else:
                print(f"Remove error ({resp.status_code}): {resp.text}")

        elif args.apps_command == "restart":
            resp = client.post(f"{url}/api/mas/{args.mas_id}/restart")
            if resp.status_code < 300:
                print(f"Success: MAS instance '{args.mas_id}' restart triggered.")
            else:
                print(f"Error ({resp.status_code}): {resp.text}")

        elif args.apps_command == "stop":
            resp = client.post(f"{url}/api/mas/{args.mas_id}/stop")
            if resp.status_code < 300:
                print(f"Success: MAS instance '{args.mas_id}' stopped.")
            else:
                print(f"Error ({resp.status_code}): {resp.text}")

        elif args.apps_command == "init":
            _handle_init(args)


def _handle_service(args: argparse.Namespace) -> None:
    """Handle generic service invocation."""
    url = args.url
    with _get_client(args) as client:
        if args.svc_command == "call":
            data = json.loads(args.data) if args.data else {}
            # Route through the Management API service invoke bridge
            resp = client.post(f"{url}/api/services/{args.service}/{args.method}/invoke", json=data)
            if resp.status_code < 300:
                try:
                    print(json.dumps(resp.json(), indent=2))
                except Exception:
                    print(resp.text)
            else:
                print(f"Error: {resp.status_code} - {resp.text}")


def _handle_pki(args: argparse.Namespace) -> None:
    """Handle PKI subcommands."""
    url = args.url
    with _get_client(args) as client:
        if args.pki_command == "requests":
            resp = client.get(f"{url}/api/pki/requests")
            if resp.status_code == 200:
                requests = resp.json()
                if not requests:
                    print("No pending PKI requests.")
                    return
                print(f"{'REQUEST ID':<40} {'NODE ID':<20} {'HOSTNAME':<20} {'TIMESTAMP'}")
                print("-" * 100)
                for req in requests:
                    print(f"{req['requestId']:<40} {req['nodeId']:<20} {req['hostname']:<20} {req['timestamp']}")
            else:
                print(f"Error: {resp.status_code} - {resp.text}")

        elif args.pki_command == "approve":
            if not os.path.exists(args.ca_key):
                print(f"Error: CA key file not found: {args.ca_key}", file=sys.stderr)
                sys.exit(1)

            password = getpass.getpass("Enter CA Key Password: ")
            with open(args.ca_key, "rb") as f:
                pfx_b64 = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "requestId": args.request_id,
                "caKeyPfxBase64": pfx_b64,
                "caKeyPassword": password,
            }
            resp = client.post(f"{url}/api/pki/approve", json=payload)
            if resp.status_code == 200:
                print("Success: Certificate signed and issued.")
            else:
                print(f"Error: {resp.status_code} - {resp.text}")

        elif args.pki_command == "generate-root":
            password = getpass.getpass("Set CA Key Password (optional): ")
            payload = {
                "subject": args.subject,
                "password": password,
                "forceSave": args.force_save,
                "addAsAnchor": True,
            }
            resp = client.post(f"{url}/api/pki/generate-root", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                pfx_b64 = data["caKeyPfxBase64"]
                with open(args.out, "wb") as f:
                    f.write(base64.b64decode(pfx_b64))
                print(f"Success: Root CA generated and saved to {args.out}")
                if args.force_save:
                    print("Genesis: Root CA force-saved to grid for auto-approval.")
            else:
                print(f"Error: {resp.status_code} - {resp.text}")

        elif args.pki_command == "anchors":
            if args.anchor_command == "add":
                with open(args.path, "r", encoding="utf-8") as f:
                    pem = f.read()
                resp = client.post(f"{url}/api/pki/anchors", json={"certificatePem": pem})
                if resp.status_code == 200:
                    print("Success: Trust anchor added.")
                else:
                    print(f"Error: {resp.status_code} - {resp.text}")
            elif args.anchor_command == "remove":
                resp = client.delete(f"{url}/api/pki/anchors/{args.thumbprint}")
                if resp.status_code == 200:
                    print("Success: Trust anchor removed.")
                else:
                    print(f"Error: {resp.status_code} - {resp.text}")

        elif args.pki_command == "revoke":
            payload = {"nodeId": args.id, "reason": args.reason}
            print(f"Revoking {args.id}...")
            resp = client.post(f"{url}/api/governance/revoke-node", json=payload)
            if resp.status_code == 200:
                print("Success: Node revoked.")
            else:
                print(f"Error: {resp.status_code} - {resp.text}")


def _generate_descriptor(class_path: str, output: str) -> None:
    """Load a class by its dotted path and generate its descriptor."""
    parts = class_path.rsplit(".", 1)
    if len(parts) != 2:
        print(
            f"Error: '{class_path}' must be a fully qualified 'module.ClassName' path.",
            file=sys.stderr,
        )
        sys.exit(1)

    module_path, class_name = parts

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        print(f"Error: Could not import module '{module_path}': {e}", file=sys.stderr)
        sys.exit(1)

    cls = getattr(module, class_name, None)
    if cls is None:
        print(
            f"Error: Class '{class_name}' not found in module '{module_path}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        save_descriptor(cls, output)
        print(f"Generated {output} for {class_path}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
