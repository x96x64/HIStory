"""HIStory: rebuild an Apple Music library on macOS from FLAC downloads with exact, verified tags."""

from pathlib import Path


def _source_version() -> str:
    """The version of a copy that is not installed: the npm package or a source tree."""
    import json
    import tomllib

    parent = Path(__file__).resolve().parent.parent
    try:
        return json.loads((parent / "package.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        pass
    try:
        return tomllib.loads((parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, ValueError, KeyError):
        return "0+unknown"


def __getattr__(name: str) -> str:
    """Resolve __version__ on first use, so that importing hist does not load importlib.metadata."""
    if name == "__version__":
        from importlib.metadata import PackageNotFoundError, version

        try:
            found = version("his-story")
        except PackageNotFoundError:
            found = _source_version()
        globals()["__version__"] = found
        return found
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
