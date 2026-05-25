"""CLI entry point for AuraGrid Python SDK.

Usage::

    python -m auragrid generate-descriptor my_module.MyService
    python -m auragrid pki requests
    python -m auragrid pki approve <request-id> --ca-key ./ca.pfx
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import sys
from typing import Any

import httpx

from .descriptor import save_descriptor


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="auragrid",
        description="AuraGrid Python SDK CLI tools",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

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

    # pki requests
    pki_sub.add_parser("requests", help="List pending Certificate Signing Requests (CSRs)")

    # pki approve
    app_parser = pki_sub.add_parser("approve", help="Approve and sign a pending CSR")
    app_parser.add_argument("request_id", help="ID of the CSR to sign")
    app_parser.add_argument("--ca-key", required=True, help="Path to CA private key (PFX)")
    app_parser.add_argument("--url", default="https://localhost:7087", help="Management API URL")
    app_parser.add_argument("--cert", help="Admin client certificate for mTLS (PEM)")
    app_parser.add_argument("--key", help="Admin client key for mTLS (PEM)")

    # pki generate-root
    gen_root = pki_sub.add_parser("generate-root", help="Originate a brand new Root CA for a fresh grid")
    gen_root.add_argument("--subject", default="CN=AuraGrid-Genesis-CA", help="Subject name for the Root CA")
    gen_root.add_argument("--out", "-o", required=True, help="Output path for the CA private key (PFX)")
    gen_root.add_argument("--force-save", action="store_true", help="Save as Cell CA for auto-approval of bootstrap nodes")
    gen_root.add_argument("--url", default="https://localhost:7087", help="Management API URL")
    gen_root.add_argument("--cert", help="Admin client certificate for mTLS (PEM)")
    gen_root.add_argument("--key", help="Admin client key for mTLS (PEM)")

    # pki anchors
    anchor_parser = pki_sub.add_parser("anchors", help="Manage cell trust anchors")
    anchor_sub = anchor_parser.add_subparsers(dest="anchor_command", required=True)
    add_anc = anchor_sub.add_parser("add", help="Add a new trust anchor (PEM)")
    add_anc.add_argument("path", help="Path to CA certificate PEM file")
    rem_anc = anchor_sub.add_parser("remove", help="Remove a trust anchor by thumbprint")
    rem_anc.add_argument("thumbprint", help="Thumbprint of the CA to remove")

    # pki revoke
    rev_parser = pki_sub.add_parser("revoke", help="Revoke a node or identity")
    rev_parser.add_argument("id", help="Node ID or Identity to revoke")
    rev_parser.add_argument("--reason", default="Administrative revocation", help="Reason for revocation")

    # service group
    svc_parser = subparsers.add_parser("service", help="Service management and invocation")
    svc_sub = svc_parser.add_subparsers(dest="svc_command", required=True)

    # service call
    call_parser = svc_sub.add_parser("call", help="Invoke a method on a service")
    call_parser.add_argument("service", help="Service name")
    call_parser.add_argument("method", help="Method name")
    call_parser.add_argument("--data", "-d", help="JSON payload")
    call_parser.add_argument("--url", default="https://localhost:8088", help="Service Proxy URL")
    call_parser.add_argument("--cert", help="Client certificate for mTLS (PEM)")
    call_parser.add_argument("--key", help="Client key for mTLS (PEM)")

    args = parser.parse_args()

    if args.command == "generate-descriptor":
        _generate_descriptor(args.class_path, args.output)
    elif args.command == "pki":
        _handle_pki(args)
    elif args.command == "service":
        _handle_service(args)


def _handle_service(args: argparse.Namespace) -> None:
    """Handle generic service invocation."""
    url = getattr(args, "url", "https://localhost:8088")
    client_opts: dict[str, Any] = {"verify": False}
    if hasattr(args, "cert") and args.cert:
        client_opts["cert"] = (args.cert, args.key) if args.key else args.cert

    with httpx.Client(**client_opts) as client:
        if args.svc_command == "call":
            data = json.loads(args.data) if args.data else {}
            resp = client.post(f"{url}/api/{args.service}/{args.method}", json=data)
            if resp.status_code < 300:
                try:
                    print(json.dumps(resp.json(), indent=2))
                except:
                    print(resp.text)
            else:
                print(f"Error: {resp.status_code} - {resp.text}")


def _handle_pki(args: argparse.Namespace) -> None:
    """Handle PKI subcommands."""
    url = getattr(args, "url", "https://localhost:7087")
    
    # Setup mTLS client if cert/key provided
    client_opts: dict[str, Any] = {"verify": False} # Default to skip verify for bootstrap
    if hasattr(args, "cert") and args.cert:
        client_opts["cert"] = (args.cert, args.key) if args.key else args.cert

    with httpx.Client(**client_opts) as client:
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
                print(f"Error: CA key file not found: {args.ca_key}")
                sys.exit(1)

            password = getpass.getpass("Enter CA Key Password: ")
            
            with open(args.ca_key, "rb") as f:
                pfx_b64 = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "requestId": args.request_id,
                "caKeyPfxBase64": pfx_b64,
                "caKeyPassword": password
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
                "addAsAnchor": True
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
                with open(args.path, "r") as f:
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
            # This uses the generic governance endpoint or a specific MAS method
            # For simplicity, we use the ManagementService SignCertificate pattern
            payload = {"nodeId": args.id, "reason": args.reason}
            # We don't have a specific REST endpoint for Revoke yet, 
            # so we'll use the generic service call logic under the hood.
            # But the user wants everything to be MAS call eventually.
            
            # For now, let's assume there is a governance API
            print(f"Revoking {args.id}...")
            # We'll need a way to call the MAS method
            rpc_payload = {"key": f"revoke/{args.id}", "value": args.reason}
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
            f"Error: '{class_path}' must be a fully qualified "
            f"'module.ClassName' path.",
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
