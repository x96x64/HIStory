"""Running external tools.

Every child process is started in its own session, so a Ctrl-C in the terminal reaches only hist, which can then
finish the current album before it stops. If hist itself is interrupted while a child runs, the child is killed.
"""
import shutil
import subprocess


class ToolError(Exception):
    """A required external tool is missing."""


def which(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise ToolError(f"{tool} was not found on PATH")
    return path


def run(args, *, text: bool = False, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run a command, capture its output, and kill it if hist is interrupted."""
    args = [str(a) for a in args]
    child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=text, errors="replace" if text else None, start_new_session=True)
    try:
        out, err = child.communicate(timeout=timeout)
    except BaseException:
        child.kill()
        child.wait()
        raise
    return subprocess.CompletedProcess(args, child.returncode, out, err)
