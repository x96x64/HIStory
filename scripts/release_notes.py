#!/usr/bin/env python3
"""Print the GitHub Release notes of a version, taken from CHANGELOG.md.

Usage: python scripts/release_notes.py VERSION   (VERSION may start with "v")

The output is the body of the changelog section "## [VERSION]" without its heading, a blank line, and the line
"**Full Changelog**: <URL>", where URL is the comparison link of that version in the changelog. The command exits
with status 1 and a message on standard error when the section or its link is missing or the section is empty.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def release_notes(text: str, version: str) -> str:
    """Return the release notes for version, or raise ValueError with the reason."""
    version = version.removeprefix("v")
    lines = text.splitlines()
    heading = re.compile(rf"^## \[{re.escape(version)}\]")
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise ValueError(f"CHANGELOG.md has no section for {version}")
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## [") or re.match(r"^\[[^\]]+\]: ", line):
            break
        body.append(line)
    section = "\n".join(body).strip("\n")
    if not section.strip():
        raise ValueError(f"The CHANGELOG.md section for {version} is empty")
    link = re.search(rf"^\[{re.escape(version)}\]: (\S+)\s*$", text, re.MULTILINE)
    if link is None:
        raise ValueError(f"CHANGELOG.md has no link reference for {version}")
    return f"{section}\n\n**Full Changelog**: {link.group(1)}\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: release_notes.py VERSION", file=sys.stderr)
        return 2
    try:
        sys.stdout.write(release_notes(CHANGELOG.read_text(encoding="utf-8"), argv[1]))
    except (OSError, ValueError) as error:
        print(f"release_notes.py: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
