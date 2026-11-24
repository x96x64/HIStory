import json
from pathlib import Path

import pytest

from hist import config


def load(tmp_path, text):
    (tmp_path / "config.toml").write_text(text, encoding="utf-8")
    return config.load(tmp_path)


@pytest.mark.parametrize(
    "text",
    [
        '[paths]\ndownloads = "x"\n',
        "[paths]\ndownloads = [1]\n",
        "[paths]\nlibrary = 3\n",
        '[convert]\nmin_free_gb = "ten"\n',
        "[convert]\nmin_free_gb = -1\n",
        "[convert]\nmin_free_gb = true\n",
        "[store]\nalbum = 1\nfile = 2\n",
        "[match]\naliases = 5\n",
        '[match.renumber."A"]\ndisc = "x"\noffset = 1\n',
        "[bogus]\nx = 1\n",
        "[paths]\ndownload = []\n",
        "paths = 3\n",
    ],
)
def test_wrong_types_and_unknown_keys_are_config_errors(tmp_path, text):
    with pytest.raises(config.ConfigError):
        load(tmp_path, text)


def test_valid_config_loads(tmp_path):
    cfg = load(tmp_path, '[paths]\ndownloads = ["d"]\n[convert]\nmin_free_gb = 2\n')
    assert cfg.downloads == (tmp_path / "d",) and cfg.min_free_gb == 2.0


def test_the_init_template_is_valid(tmp_path):
    cfg = load(tmp_path, config.TEMPLATE)
    assert cfg.downloads_auto and cfg.evacuation == Path("~/Desktop/HIStory Evacuated").expanduser()


def test_empty_downloads_use_the_usual_service_folders(tmp_path):
    cfg = load(tmp_path, "[paths]\ndownloads = []\n")
    assert cfg.downloads_auto and Path("~/Music/mora").expanduser() in cfg.downloads
    assert Path("~/Downloads").expanduser() not in cfg.downloads
    assert cfg.present_downloads == []
    qobuz = Path("~/Music/Qobuz").expanduser()
    qobuz.mkdir(parents=True)
    assert cfg.present_downloads == [qobuz]


def test_listed_downloads_turn_detection_off(tmp_path):
    cfg = load(tmp_path, '[paths]\ndownloads = ["d"]\n')
    assert not cfg.downloads_auto and cfg.downloads == (tmp_path / "d",)


def test_doctor_does_not_warn_about_absent_download_folders(tmp_path, capsys):
    from hist import cli

    (tmp_path / "config.toml").write_text('[paths]\ndownloads = ["~/Music/mora", "here"]\n')
    (tmp_path / "here").mkdir()
    cli.main(["--home", str(tmp_path), "doctor", "--json"])
    report = json.loads(capsys.readouterr().out)
    downloads = [c for c in report["checks"] if c["text"].startswith("downloads")]
    assert [c["status"] for c in downloads] == ["ok"]
    assert not any("mora" in c["text"] for c in report["checks"] if c["status"] != "ok")
    assert any("mora" in i and "skipped" in i for i in report["info"])
