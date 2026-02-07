"""CLI entry point for AuraGrid Python SDK.

Usage::

    python -m auragrid generate-descriptor my_module.MyService
    python -m auragrid generate-descriptor my_module.MyService --output service-descriptor.json
"""

from __future__ import annotations

import argparse
import importlib
import sys

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

    args = parser.parse_args()

    if args.command == "generate-descriptor":
        _generate_descriptor(args.class_path, args.output)


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
