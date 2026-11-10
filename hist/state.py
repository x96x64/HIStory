"""Small files under <home>/state: progress records, locks, and history copies."""
import fcntl
import json
import os
import shutil
import time
from pathlib import Path

from hist.errors import HistError


def write_json(path: Path, data) -> None:
    """Write JSON atomically (a temporary file, then a rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


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


def keep_history(path: Path, history_dir: Path) -> Path | None:
    """Copy path into history_dir under a name that is never reused."""
    if not path.exists():
        return None
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = history_dir / f"{path.name}.{stamp}"
    n = 2
    while target.exists():
        target = history_dir / f"{path.name}.{stamp}-{n}"
        n += 1
    shutil.copy2(path, target)
    return target


class LockHeld(HistError):
    def __init__(self, path: Path, pid: str):
        super().__init__(f"{path.stem} is already running (pid {pid or '?'})")
        self.pid = pid


class Lock:
    """An exclusive lock on <state>/<name>.lock holding the owner's process id."""

    def __init__(self, state_dir: Path, name: str):
        self.path = state_dir / f"{name}.lock"
        self.handle = None

    def acquire(self) -> "Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+")
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
    """The process id holding <name>.lock, or None when nobody holds it."""
    path = state_dir / f"{name}.lock"
    if not path.exists():
        return None
    with open(path, "a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.seek(0)
            text = handle.read().strip()
            return int(text) if text.isdigit() else -1
        fcntl.flock(handle, fcntl.LOCK_UN)
    return None
