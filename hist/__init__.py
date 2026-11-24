"""HIStory: rebuild an Apple Music library on macOS from FLAC downloads with exact, verified tags."""

import json
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _source_version() -> str:
    """The version of a copy that is not installed: the npm package or a source tree."""
    parent = Path(__file__).resolve().parent.parent
    try:
        return json.loads((parent / "package.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        pass
    try:
        return tomllib.loads((parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, ValueError, KeyError):
        return "0+unknown"


try:
    __version__ = version("his-story")
except PackageNotFoundError:
    __version__ = _source_version()
