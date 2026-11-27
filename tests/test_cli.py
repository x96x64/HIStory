import json
import signal
import sys
from pathlib import Path

import pytest

from hist import __version__
from hist.cli import main


def test_version(capsys):
    with pytest.raises(SystemExit) as exit_:
        main(["--version"])
    assert exit_.value.code == 0
    assert capsys.readouterr().out.strip() == f"hist {__version__}"


def test_no_command_prints_help(capsys):
    assert main([]) == 2
    assert "usage: hist" in capsys.readouterr().out


def test_unknown_command_is_a_usage_error():
    with pytest.raises(SystemExit) as exit_:
        main(["frobnicate"])
    assert exit_.value.code == 2


def test_init_creates_an_empty_catalog(tmp_path):
    home = tmp_path / "home"
    assert main(["init"]) == 0
    assert (home / "config.toml").exists()
    assert json.loads((home / "tracks.json").read_text()) == {"format": 2, "tracks": []}
    assert (home / "covers").is_dir() and not (home / "specs").exists()


def test_init_from_copies_a_catalog_and_refuses_to_overwrite(tmp_path):
    src = tmp_path / "shipped"
    (src / "covers").mkdir(parents=True)
    record = {
        "file": "A/B/01 T.m4a",
        "tags": {
            "ItemList:Title": "T",
            "ItemList:Album": "B",
            "ItemList:AlbumArtist": "A",
            "ItemList:Artist": "A",
            "ItemList:TrackNumber": "1 of 1",
            "ItemList:DiskNumber": "1 of 1",
            "ItemList:ContentCreateDate": "2000:01:01 00:00:00Z",
        },
        "blobs": {},
    }
    (src / "tracks.json").write_text(json.dumps({"format": 2, "tracks": [record]}))
    (src / "config.toml").write_text("[paths]\ndownloads = []\n")
    assert main(["init", "--from", str(src)]) == 0
    assert main(["init", "--from", str(src)]) == 2
    assert main(["init", "--from", str(src), "--force"]) == 0


def test_dates_on_an_empty_catalog(capsys):
    assert main(["init"]) == 0
    assert main(["dates", "list"]) == 0
    assert main(["dates", "check"]) == 0


def test_hist_never_adds_albums_to_music(capsys):
    with pytest.raises(SystemExit):
        main(["register"])
    from hist.cli import build_parser

    assert "register" not in build_parser().format_help()


def test_stop_with_nothing_running(capsys):
    main(["init"])
    assert main(["stop"]) == 0
    assert "Nothing is running" in capsys.readouterr().out


def test_doctor_reports_a_broken_catalog_instead_of_crashing(tmp_path, capsys):
    main(["init"])
    (tmp_path / "home" / "tracks.json").write_text("{not json")
    assert main(["doctor"]) == 1
    assert "problems" in capsys.readouterr().out


def test_catalog_remove_from_the_command_line(tmp_path, capsys):
    main(["init"])
    record = {
        "file": "A/B/01 T.m4a",
        "tags": {
            "ItemList:Title": "T",
            "ItemList:Album": "B",
            "ItemList:AlbumArtist": "A",
            "ItemList:Artist": "A",
            "ItemList:TrackNumber": "1 of 1",
            "ItemList:DiskNumber": "1 of 1",
            "ItemList:ContentCreateDate": "2000:01:01 00:00:00Z",
        },
        "blobs": {},
    }
    (tmp_path / "home" / "tracks.json").write_text(json.dumps({"format": 2, "tracks": [record]}))
    assert main(["catalog", "remove", "B", "--dry-run"]) == 0
    assert "Would remove B" in capsys.readouterr().out
    assert main(["catalog", "remove", "B"]) == 0
    assert json.loads((tmp_path / "home" / "tracks.json").read_text())["tracks"] == []
    assert main(["catalog", "remove", "B"]) == 1


def _json_error(capsys) -> dict:
    return json.loads(capsys.readouterr().err)["error"]


def test_status_and_doctor_json_shape(capsys):
    main(["init"])
    capsys.readouterr()
    assert main(["status", "--json"]) in (0, 1)
    assert isinstance(json.loads(capsys.readouterr().out), dict)
    main(["doctor", "--json"])
    assert isinstance(json.loads(capsys.readouterr().out), dict)


def test_os_error_is_a_clean_json_error(tmp_path, capsys):
    main(["init"])
    capsys.readouterr()
    assert main(["catalog", "edit", str(tmp_path / "missing.json"), "--json"]) == 1
    error = _json_error(capsys)
    assert error["code"] in ("error", "catalog") and "missing.json" in error["message"]


def test_bad_json_and_bad_bytes_are_clean_errors(tmp_path, capsys):
    main(["init"])
    capsys.readouterr()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert main(["catalog", "edit", str(bad), "--json"]) == 1
    assert _json_error(capsys)["code"] in ("error", "catalog")
    bad.write_bytes(b"\xff\xfe\x00\xff")
    assert main(["catalog", "edit", str(bad), "--json"]) == 1
    assert _json_error(capsys)["code"] in ("error", "catalog")


def test_os_error_without_json_has_no_traceback(tmp_path, capsys):
    main(["init"])
    capsys.readouterr()
    assert main(["catalog", "edit", str(tmp_path / "missing.json")]) == 1
    err = capsys.readouterr().err
    assert err.startswith("hist: error:") and "Traceback" not in err


@pytest.mark.parametrize(
    "raised",
    [
        PermissionError(13, "Permission denied", "/x"),
        ValueError("bad"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"),
    ],
)
def test_unexpected_errors_map_to_code_error(capsys, monkeypatch, raised):
    from hist import doctor

    main(["init"])
    capsys.readouterr()

    def boom(*args, **kwargs):
        raise raised

    monkeypatch.setattr(doctor, "run", boom)
    assert main(["doctor", "--json"]) == 1
    assert _json_error(capsys)["code"] == "error"


def test_usage_error_is_json_with_json_option(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["catalog", "show", "--json", "--bogus"])
    assert exit_info.value.code == 2
    assert _json_error(capsys)["code"] == "usage"
    with pytest.raises(SystemExit) as exit_info:
        main(["--bogus"])
    assert exit_info.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_stop_with_a_stale_pid_and_without_a_lock(tmp_path, capsys):
    main(["init"])
    lock = tmp_path / "home" / "state" / "convert.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    for text in ("2147483646", "-1", "junk", ""):
        lock.write_text(text)
        assert main(["stop"]) == 0
        assert "Nothing is running" in capsys.readouterr().out


def test_stop_signals_the_holder(tmp_path, capsys, monkeypatch):
    import os

    from hist import log as hist_log
    from hist import state

    main(["init"])
    lock = tmp_path / "home" / "state" / "convert.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    sent = []
    real = os.kill
    monkeypatch.setattr(os, "kill", lambda pid, sig: sent.append((pid, sig)) if sig else real(pid, sig))
    try:
        with state.Lock(lock.parent, "convert"):
            assert main(["-q", "stop"]) == 0
    finally:
        hist_log.setup()  # later tests that do not call main() rely on a console handler at the default level
    assert sent == [(os.getpid(), signal.SIGTERM)]
    assert "Asked hist" in capsys.readouterr().out


def test_holder_ignores_a_live_pid_without_a_held_lock(tmp_path, capsys):
    import os

    from hist import state

    main(["init"])
    capsys.readouterr()
    lock = tmp_path / "home" / "state" / "convert.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()))
    assert state.holder(tmp_path / "home" / "state", "convert") is None
    assert main(["stop"]) == 0
    assert "Nothing is running." in capsys.readouterr().out


def test_holder_does_not_take_the_lock(tmp_path):
    import os

    from hist import state

    with state.Lock(tmp_path, "catalog"):
        assert state.holder(tmp_path, "catalog") == os.getpid()
    assert state.holder(tmp_path, "catalog") is None


def test_folder_of_outside_the_library(tmp_path):
    from hist.cli import folder_of

    album = {"tracks": [type("T", (), {"path": "/elsewhere/A/B/01.m4a"})()]}
    assert folder_of(album, tmp_path) == "/elsewhere/A/B"
    assert folder_of(album, Path("/elsewhere")) == "A/B"


def test_stopper_first_signal_asks_second_stops_at_once():
    from hist import runtime

    for first in (signal.SIGINT, signal.SIGTERM):
        for second in (signal.SIGINT, signal.SIGTERM):
            stopper = runtime.Stopper()
            stopper._handle(first, None)
            assert stopper.requested
            with pytest.raises(runtime.Stopped):
                stopper.check()
            with pytest.raises(KeyboardInterrupt):
                stopper._handle(second, None)


def test_stopper_stops_at_once_while_waiting():
    from hist import runtime

    stopper = runtime.Stopper()
    with pytest.raises(runtime.Stopped) as stopped, stopper.waiting():
        stopper._handle(signal.SIGTERM, None)
    assert stopped.value.exit_code == 128 + signal.SIGTERM


def test_proc_run_captures_output_and_reports_a_missing_tool():
    from hist import proc

    result = proc.run([sys.executable, "-c", "import sys; print('a'); sys.stderr.write('b'); sys.exit(3)"], text=True)
    assert (result.returncode, result.stdout.strip(), result.stderr) == (3, "a", "b")
    with pytest.raises(proc.ToolError):
        proc.run(["hist-no-such-tool"])


def test_proc_run_kills_the_child_on_timeout():
    import subprocess

    from hist import proc

    with pytest.raises(subprocess.TimeoutExpired):
        proc.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.3)


def test_version_is_lazy():
    import subprocess

    code = "import sys, hist; assert 'importlib.metadata' not in sys.modules; print(hist.__version__)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
