"""Running external tools.

Every child process is started in its own session, so a Ctrl-C in the terminal reaches only hist, which can then
finish the current album before it stops. If hist itself is interrupted while a child runs, the child is killed.
"""

import shutil
import subprocess
import sys

from hist.errors import HistError


class ToolError(HistError):
    """A required external tool is missing."""

    code = "tool"


INSTALL = {
    "ffmpeg": "brew install ffmpeg",
    "ffprobe": "brew install ffmpeg",
    "flac": "brew install flac",
    "metaflac": "brew install flac",
    "exiftool": "brew install exiftool",
    "SetFile": "xcode-select --install (macOS only)",
    "osascript": "available on macOS only",
}


def missing(tool: str) -> str:
    """The message for a tool that is not installed, with a typical way to install it."""
    how = INSTALL.get(tool)
    return f"{tool} was not found on PATH" + (f"; install it, for example with: {how}" if how else "")


class MacOnly(HistError):
    code = "platform"


def require_macos(what: str) -> None:
    """Fail at once, before any work, when what needs macOS and this is another system."""
    if sys.platform != "darwin":
        raise MacOnly(
            f"{what} needs macOS (the Music app, osascript or SetFile); this system is {sys.platform}. "
            "Catalog commands such as 'hist catalog list', 'edit' and 'export' work everywhere"
        )


def which(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise ToolError(missing(tool))
    return path


def run(args, *, text: bool = False, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run a command, capture its output, and kill it if hist is interrupted."""
    args = [str(a) for a in args]
    try:
        child = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            errors="replace" if text else None,
            start_new_session=True,
        )
    except FileNotFoundError:
        raise ToolError(missing(args[0])) from None
    try:
        out, err = child.communicate(timeout=timeout)
    except BaseException:
        child.kill()
        child.wait()
        raise
    return subprocess.CompletedProcess(args, child.returncode, out, err)
