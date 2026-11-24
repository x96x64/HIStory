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
    assert load(tmp_path, config.TEMPLATE).downloads == ()
