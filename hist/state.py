"""Small files under <home>/state: progress records, locks, and backups."""

import fcntl
import json
import os
import re
import shutil
import stat
import tempfile
import time
from pathlib import Path

from hist.errors import HistError


def write_bytes(path: Path, data: bytes) -> None:
    """Write a file durably and atomically: a temporary file in the same folder, fsync, then a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def write_json(path: Path, data) -> None:
    """Write JSON atomically and durably (see write_bytes)."""
    write_bytes(path, (json.dumps(data, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))


def read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


class Progress:
    """Album names recorded as finished in one JSON file (converted.json, added.json)."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        return read_json(self.path, {})

    def names(self) -> set:
        return set(self.load())

    def add(self, name: str, **details) -> None:
        data = self.load()
        data[name] = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), **details}
        write_json(self.path, dict(sorted(data.items())))

    def remove(self, name: str) -> bool:
        data = self.load()
        if data.pop(name, None) is None:
            return False
        write_json(self.path, data)
        return True


def converted(state_dir: Path) -> Progress:
    return Progress(state_dir / "converted.json")


def added(state_dir: Path) -> Progress:
    """Albums found in the library, checked against the catalog and dated."""
    return Progress(state_dir / "added.json")


def unique(path: Path) -> Path:
    """path, or path-2, path-3 ... if it already exists."""
    target, n = path, 2
    while target.exists():
        target = path.with_name(f"{path.name}-{n}")
        n += 1
    return target


class Backup:
    """The folder state/backups/<time>-<command> that keeps the files one command changes, made on first use."""

    def __init__(self, state_dir: Path, command: str):
        self.base = state_dir / "backups" / f"{time.strftime('%Y%m%d-%H%M%S')}-{command}"
        self.path: Path | None = None

    def folder(self) -> Path:
        if self.path is None:
            self.path = unique(self.base)
            self.path.mkdir(parents=True)
        return self.path

    def keep(self, path: Path, name: str | None = None) -> Path | None:
        """Copy path into the folder, as name (for example covers/<digest>) or under its own name.

        A path that does not exist is recorded as an empty marker file '<name>.absent' and None is returned.
        """
        target = self.folder() / (name or path.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            target.with_name(target.name + ".absent").touch()
            return None
        shutil.copy2(path, target)
        return target


OLD_COPY = re.compile(r"^(.+)\.(\d{8}-\d{6})(?:-(\d+))?$")
OLD_SNAPSHOT = re.compile(r"^retag-(\d{8}-\d{6})(-\d+)?$")
COVER_NAME = re.compile(r"^[0-9a-f]{64}$")


def migrate_backups(state_dir: Path) -> int:
    """Move the copies in state/history/ and state/snapshots/ (before 2.2.0) into state/backups/.

    Copies in history/ with the same time go into one folder <time>-catalog; a snapshot retag-<time> becomes
    <time>-retag. Anything else is left where it is. Returns the number of folders made.
    """
    backups = state_dir / "backups"
    made = 0
    history = state_dir / "history"
    if history.is_dir():
        groups: dict = {}
        for f in sorted(history.iterdir()):
            m = OLD_COPY.match(f.name)
            if f.is_file() and m:
                groups.setdefault((m[2], m[3] or ""), []).append((f, m[1]))
        for (stamp, n), files in sorted(groups.items()):
            dest = unique(backups / (f"{stamp}-catalog" + (f"-{n}" if n else "")))
            for f, name in files:
                target = dest / ("covers/" + name if COVER_NAME.match(name) else name)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(f, target)
            made += 1
    snapshots = state_dir / "snapshots"
    if snapshots.is_dir():
        for d in sorted(snapshots.iterdir()):
            m = OLD_SNAPSHOT.match(d.name)
            if d.is_dir() and m:
                backups.mkdir(parents=True, exist_ok=True)
                os.replace(d, unique(backups / f"{m[1]}-retag{m[2] or ''}"))
                made += 1
    for old in (history, snapshots):
        if old.is_dir():
            (old / ".DS_Store").unlink(missing_ok=True)
            if not any(old.iterdir()):
                old.rmdir()
    return made


class LockHeld(HistError):
    code = "locked"

    def __init__(self, path: Path, pid: str):
        super().__init__(f"{path.stem} is already running (pid {pid or '?'})")
        self.pid = pid
        self.name = path.stem


class Lock:
    """An exclusive lock on <state>/<name>.lock holding the owner's process id."""

    def __init__(self, state_dir: Path, name: str):
        self.path = state_dir / f"{name}.lock"
        self.handle = None

    def acquire(self) -> "Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+")  # noqa: SIM115 - kept open as the lock
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.seek(0)
            pid = handle.read().strip()
            handle.close()
            raise LockHeld(self.path, pid) from None
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self.handle = handle
        return self

    def release(self) -> None:
        if self.handle:
            self.handle.seek(0)
            self.handle.truncate()
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()


def holder(state_dir: Path, name: str) -> int | None:
    """The process id holding <name>.lock, or None when nobody holds it.

    The owner writes its id on acquiring and clears the file on releasing; an id whose process is gone is stale.
    Only when the file names a live process is the lock probed, with a shared, non-blocking lock that is released
    at once, so a concurrent writer is hardly disturbed; a live id without a held lock (a reused id) is stale.
    """
    try:
        text = (state_dir / f"{name}.lock").read_text().strip()
    except OSError:
        return None
    if not text.isdigit() or int(text) <= 0:
        return None
    pid = int(text)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    try:
        fd = os.open(state_dir / f"{name}.lock", os.O_RDONLY)
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        return pid
    except OSError:
        return pid
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return None
    finally:
        os.close(fd)
