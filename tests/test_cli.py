import json

import pytest

from history_music import __version__
from history_music.cli import main


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
    assert (home / "covers").is_dir() and (home / "specs").is_dir()


def test_init_from_copies_a_catalog_and_refuses_to_overwrite(tmp_path):
    src = tmp_path / "shipped"
    (src / "covers").mkdir(parents=True)
    record = {"file": "A/B/01 T.m4a", "tags": {"ItemList:Title": "T", "ItemList:Album": "B",
                                               "ItemList:AlbumArtist": "A", "ItemList:Artist": "A",
                                               "ItemList:TrackNumber": "1 of 1", "ItemList:DiskNumber": "1 of 1",
                                               "ItemList:ContentCreateDate": "2000:01:01 00:00:00Z"}, "blobs": {}}
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
    from history_music.cli import build_parser
    assert "register" not in build_parser().format_help()


def test_stop_with_nothing_running(capsys):
    main(["init"])
    assert main(["stop"]) == 0
    assert "Nothing is running" in capsys.readouterr().out
