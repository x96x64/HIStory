import base64
import hashlib
import json

import pytest

from hist import state, tags


def test_write_bytes_and_write_json_replace_atomically(tmp_path):
    target = tmp_path / "sub" / "file.json"
    state.write_json(target, {"a": 1})
    state.write_json(target, {"a": 2})
    assert json.loads(target.read_text()) == {"a": 2}
    state.write_bytes(tmp_path / "blob", b"\x00\x01")
    assert (tmp_path / "blob").read_bytes() == b"\x00\x01"
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["blob", "file.json"]


def test_a_failed_write_leaves_the_old_file_and_no_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "file.json"
    state.write_json(target, {"a": 1})

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(state.os, "replace", fail)
    with pytest.raises(OSError):
        state.write_json(target, {"a": 2})
    assert json.loads(target.read_text()) == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["file.json"]


def test_write_bytes_syncs_the_file_before_the_rename(tmp_path, monkeypatch):
    calls = []
    real_fsync, real_replace = state.os.fsync, state.os.replace
    monkeypatch.setattr(state.os, "fsync", lambda fd: (calls.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(state.os, "replace", lambda a, b: (calls.append("replace"), real_replace(a, b))[1])
    state.write_bytes(tmp_path / "x", b"data")
    assert calls[:2] == ["fsync", "replace"]


def test_store_blob_writes_the_cover_by_its_digest(tmp_path):
    digest = tags.store_blob(base64.b64encode(b"picture").decode(), tmp_path / "covers")
    assert (tmp_path / "covers" / digest).read_bytes() == b"picture"
    assert digest == hashlib.sha256(b"picture").hexdigest()
    assert [p.name for p in (tmp_path / "covers").iterdir()] == [digest]


def test_write_bytes_gives_a_new_file_the_umask_mode_and_keeps_the_mode_of_an_old_one(tmp_path):
    import os

    from hist import state

    umask = os.umask(0)
    os.umask(umask)
    new = tmp_path / "new.json"
    state.write_bytes(new, b"x")
    assert new.stat().st_mode & 0o777 == 0o666 & ~umask
    old = tmp_path / "old.json"
    old.write_bytes(b"a")
    old.chmod(0o644)
    state.write_bytes(old, b"b")
    assert old.stat().st_mode & 0o777 == 0o644
