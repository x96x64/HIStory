#!/usr/bin/env python3
"""Check that pyproject.toml, npm/package.json and CHANGELOG.md name the same version.

Usage: python scripts/check_versions.py [TAG]   (TAG such as v2.4.0 is compared as well)
"""

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def versions() -> dict[str, str]:
    found = {
        "pyproject.toml": tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"],
        "npm/package.json": json.loads((ROOT / "npm" / "package.json").read_text(encoding="utf-8"))["version"],
    }
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[(\d+\.\d+\.\d+[^\]]*)\]", changelog, re.MULTILINE)
    found["CHANGELOG.md"] = match.group(1) if match else "(none)"
    return found


def main(argv: list[str]) -> int:
    found = versions()
    if argv:
        found["tag"] = argv[0].removeprefix("v")
    for name, value in found.items():
        print(f"{name}: {value}")
    if len(set(found.values())) != 1:
        print("error: the versions differ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
