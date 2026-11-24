"""Tests for scripts/release_notes.py."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("release_notes", ROOT / "scripts" / "release_notes.py")
release_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_notes)

SAMPLE = """# Changelog

## [Unreleased]

## [1.1.0] - 2026-01-02

### Added

- A thing.

## [1.0.0] - 2026-01-01

## [0.9.0] - 2025-12-01

- Old.

[Unreleased]: https://example.test/compare/v1.1.0...HEAD
[1.1.0]: https://example.test/compare/v1.0.0...v1.1.0
[1.0.0]: https://example.test/releases/tag/v1.0.0
"""


def test_section_and_full_changelog_line():
    out = release_notes.release_notes(SAMPLE, "v1.1.0")
    assert out == "### Added\n\n- A thing.\n\n**Full Changelog**: https://example.test/compare/v1.0.0...v1.1.0\n"
    assert release_notes.release_notes(SAMPLE, "1.1.0") == out


def test_missing_empty_or_unlinked_section_fails():
    with pytest.raises(ValueError, match="no section"):
        release_notes.release_notes(SAMPLE, "2.0.0")
    with pytest.raises(ValueError, match="empty"):
        release_notes.release_notes(SAMPLE, "1.0.0")
    with pytest.raises(ValueError, match="link reference"):
        release_notes.release_notes(SAMPLE, "0.9.0")


def test_every_released_version_has_notes():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    import re

    for version in re.findall(r"^## \[(\d[^\]]*)\]", text, re.MULTILINE):
        assert release_notes.release_notes(text, version).endswith("\n")


def test_command_line(capsys):
    assert release_notes.main(["release_notes.py", "0.0.0"]) == 1
    assert "no section" in capsys.readouterr().err
    assert release_notes.main(["release_notes.py", "2.4.0"]) == 0
    assert "**Full Changelog**: https://github.com/x96x64/HIStory/compare/v2.3.0...v2.4.0" in capsys.readouterr().out
