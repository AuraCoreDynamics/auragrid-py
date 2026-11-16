#!/usr/bin/env python3
"""
Local CI verification script for auragrid-py.

Mirrors the exact checks performed by GitHub Actions CI:
  1. Test suite execution (pytest tests/ -v -m "not sovereignty")
  2. Package distribution build (python -m build)
  3. Package metadata check (twine check dist/*)
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_step(name: str, cmd: list[str]) -> bool:
    print(f"\n{'=' * 60}")
    print(f"==> Step: {name}")
    print(f"==> Command: {' '.join(cmd)}")
    print(f"{'=' * 60}\n")
    env = os.environ.copy()
    existing_py_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{REPO_ROOT};{REPO_ROOT.parent / 'auragrid-api' / 'src'};{existing_py_path}"
    env["PYTEST_ADDOPTS"] = "-p no:napari"
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    if res.returncode != 0:
        print(f"\n[FAILED] Step '{name}' exited with code {res.returncode}")
        return False
    print(f"\n[PASSED] Step '{name}' succeeded.")
    return True


def main() -> int:
    steps = [
        ("Unit Tests (Pytest)", [sys.executable, "-m", "pytest", "tests/", "-v", "-m", "not sovereignty"]),
        ("Package Build", [sys.executable, "-m", "build"]),
        ("Package Validation (Twine)", [sys.executable, "-m", "twine", "check", "dist/*"]),
    ]

    for name, cmd in steps:
        if not run_step(name, cmd):
            print("\n❌ CI pre-push verification failed. Fix errors above before pushing.")
            return 1

    print("\n✅ All CI checks passed successfully! Ready for push.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
