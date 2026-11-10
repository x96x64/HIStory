import datetime
import json
import os
import shutil
import signal
import subprocess
import threading

import pytest

from conftest import needs_tools, spec
from history_music import catalog, convert, library, runtime, state, watch

pytestmark = needs_tools


def write_spec(env, name, the_spec):
    (env.home / "specs").mkdir(exist_ok=True)
    (env.home / "specs" / f"{name}.json").write_text(json.dumps(the_spec))


def test_watch_adds_specs_converts_and_ends_by_itself(env):
    first = env.download("First", "First", "Band", ["a", "b"])
    env.add_album(spec("First", "Band", "2000-01-01", ["A", "B"]), first)
    env.download("Second (Deluxe)", "Second (Deluxe)", "Band", ["c", "d"], base_freq=900)
    write_spec(env, "second", spec("Second", "Band", "2001-01-01", ["C", "D"]))
    code = watch.run(env.config(), convert.Options(), runtime.Stopper(), interval=0.1, convert_only=True)
    assert code == 0
    assert state.converted(env.config().state).names() == {"First", "Second"}
    assert {a["name"] for a in catalog.albums(env.config())} == {"First", "Second"}


def test_watch_stops_when_asked(env):
    first = env.download("First", "First", "Band", ["a", "b"])
    env.add_album(spec("First", "Band", "2000-01-01", ["A", "B"]), first)
    env.download("Later", "Later", "Band", ["x"])          # one of two tracks: never complete
    write_spec(env, "later", spec("Later", "Band", "2002-01-01", ["X", "Y"]))
    stopper = runtime.Stopper()
    threading.Timer(1.5, lambda: setattr(stopper, "signum", signal.SIGTERM)).start()
    with pytest.raises(runtime.Stopped) as stopped:
        watch.run(env.config(), convert.Options(), stopper, interval=0.2)
    assert stopped.value.exit_code == 143
    assert "First" in state.converted(env.config().state).names()


def prepared(env):
    for i, name in enumerate(("Alpha", "Beta")):
        d = env.download(name, name, "Band", ["s", "t"], base_freq=300 + 200 * i)
        env.add_album(spec(name, "Band", f"200{i}-0{i + 1}-01", ["S", "T"]), d)
    (env.home / "dates.json").write_text(json.dumps({"entries": [
        {"kind": "artist", "path": "Band", "date": "1990-01-01"},
        {"kind": "album", "path": "Band/Alpha", "date": "2000-01-01"},
        {"kind": "album", "path": "Band/Beta", "date": "2001-02-01"}]}))
    convert.run_once(env.config(), convert.Options())


def add_in_music(env, name):
    """What the Music app does when you add an album: copy its files into the library's Artist/Album folder."""
    dest = env.library / "Band" / name
    dest.mkdir(parents=True)
    for f in (env.downloads / "Band" / name).glob("*.m4a"):
        shutil.copy2(f, dest / f.name)


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(library, "SETTLE_SECONDS", 0)


def test_albums_you_add_are_checked_dated_and_forgotten_when_removed(env, quick):
    prepared(env)
    cfg = env.config()
    follower = library.Follower(cfg)
    assert follower.missing() == ["Alpha", "Beta"]
    add_in_music(env, "Alpha")
    follower.look()                       # first look: the folder is new
    assert follower.look() == 1           # second look: unchanged, so it is checked and dated
    assert follower.missing() == ["Beta"]
    when = datetime.datetime(2000, 1, 1).timestamp()
    assert os.stat(cfg.library / "Band" / "Alpha" / "01 S.m4a").st_mtime == when
    assert os.stat(cfg.library / "Band").st_mtime == datetime.datetime(1990, 1, 1).timestamp()
    shutil.rmtree(cfg.library / "Band" / "Alpha")
    follower.look()
    assert follower.missing() == ["Alpha", "Beta"]


def test_an_album_whose_files_differ_is_not_dated(env, quick):
    prepared(env)
    cfg = env.config()
    add_in_music(env, "Alpha")
    victim = cfg.library / "Band" / "Alpha" / "01 S.m4a"
    subprocess.run(["exiftool", "-q", "-overwrite_original", "-ItemList:Genre=Rock", str(victim)], check=True)
    follower = library.Follower(cfg)
    follower.look()
    assert follower.look() == 0
    assert "Alpha" in follower.missing()


def test_watch_ends_when_every_album_is_converted_and_added(env, quick):
    prepared(env)
    add_in_music(env, "Alpha")
    add_in_music(env, "Beta")
    assert watch.run(env.config(), convert.Options(), runtime.Stopper(), interval=0.1) == 0
    assert state.added(env.config().state).names() == {"Alpha", "Beta"}


def test_convert_only_does_not_wait_for_the_library(env):
    prepared(env)
    assert watch.run(env.config(), convert.Options(), runtime.Stopper(), interval=0.1, convert_only=True) == 0
    assert state.added(env.config().state).names() == set()


def test_watch_ends_at_once_when_everything_is_already_in_the_library(env, quick):
    prepared(env)
    add_in_music(env, "Alpha")
    add_in_music(env, "Beta")
    (env.home / "state" / "converted.json").unlink()      # converted elsewhere; the downloads are gone
    for f in env.downloads.rglob("*.m4a"):
        f.unlink()
    assert watch.run(env.config(), convert.Options(), runtime.Stopper(), interval=0.1) == 0
