"""HIStory: rebuild an Apple Music library on macOS from FLAC downloads with exact, verified tags."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("his-story")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0+unknown"
