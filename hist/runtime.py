"""Stopping long-running commands cleanly, and keeping the Mac awake while they run.

The first Ctrl-C (SIGINT) or a SIGTERM from 'hist stop' asks the command to stop after the album it is working on.
While the command is only waiting (between albums, or for Enter), it stops at once. A second signal, SIGINT or
SIGTERM, stops at once.
"""

import os
import shutil
import signal
import subprocess
from contextlib import contextmanager

from hist.log import log


class Stopped(Exception):
    def __init__(self, signum: int):
        super().__init__("stopped")
        self.exit_code = 128 + signum


class Stopper:
    def __init__(self):
        self.signum = None
        self.idle = False

    def install(self) -> "Stopper":
        signal.signal(signal.SIGINT, self._handle)
        signal.signal(signal.SIGTERM, self._handle)
        return self

    def _handle(self, signum, frame):
        if self.signum is not None:
            raise KeyboardInterrupt
        self.signum = self.signum or signum
        if self.idle:
            raise Stopped(self.signum)
        log.info("Stopping after the current album (press Ctrl-C again to stop now).")

    @property
    def requested(self) -> bool:
        return self.signum is not None

    def check(self) -> None:
        if self.signum is not None:
            raise Stopped(self.signum)

    @contextmanager
    def waiting(self):
        """Mark a stretch of pure waiting: a stop request ends it at once."""
        self.check()
        self.idle = True
        try:
            yield
        finally:
            self.idle = False


def keep_awake() -> None:
    """Hold off idle sleep until this process exits (macOS caffeinate)."""
    tool = shutil.which("caffeinate")
    if tool:
        subprocess.Popen(
            [tool, "-i", "-w", str(os.getpid())],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
