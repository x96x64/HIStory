"""Test fixtures: a scratch home and synthetic FLAC downloads.

Nothing here touches the real Music library: HOME and HISTORY_HOME point into a temporary folder, and any attempt
to run osascript fails the test.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from hist import catalog, config, music_app, tags

TOOLS = ("ffmpeg", "ffprobe", "flac", "metaflac", "exiftool")
needs_tools = pytest.mark.skipif(any(shutil.which(t) is None for t in TOOLS), reason="audio tools are not installed")
needs_setfile = pytest.mark.skipif(shutil.which("SetFile") is None, reason="SetFile is not installed (macOS only)")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("HISTORY_HOME", str(tmp_path / "home"))

    def refuse(self, *args, **kwargs):
        raise AssertionError("a test tried to talk to the real Music app")

    monkeypatch.setattr(music_app.MusicApp, "osa", refuse)
    tags.similarity.cache_clear()


def run(*args):
    subprocess.run([str(a) for a in args], check=True, capture_output=True)


def make_cover(path: Path, color: str) -> Path:
    run("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=32x32", "-frames:v", "1", path)
    return path


def make_flac(path: Path, seconds: float, freq: int, cover: Path | None, **vorbis) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    run(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={freq}:duration={seconds}",
        "-ac",
        "2",
        "-ar",
        "44100",
        "-sample_fmt",
        "s16",
        path,
    )
    cmd = ["metaflac", "--remove-all-tags"] + [f"--set-tag={k.upper()}={v}" for k, v in vorbis.items()]
    cmd += ["--set-tag=COMMENT=download junk", "--set-tag=ORGANIZATION=Some Label"]
    if cover:
        cmd.append(f"--import-picture-from=3||||{cover}")
    run(*cmd, path)
    os.utime(path, (1, 1))  # old enough to count as settled
    return path


def spec(album, artist, release, titles, discs=1):
    tracks = []
    for i, title in enumerate(titles):
        disc = 1 if discs == 1 else (1 if i < (len(titles) + 1) // 2 else 2)
        number = i + 1 if disc == 1 else i + 1 - (len(titles) + 1) // 2
        tracks.append(
            {"disc": disc, "track": number, "title": title, "artist": artist, "composer": "A Writer", "genre": "Pop"}
        )
    return {
        "album": album,
        "album_artist": artist,
        "release": release,
        "discs": discs,
        "copyright": "(P) Example Records",
        "tracks": tracks,
    }


class Env:
    def __init__(self, root: Path):
        self.root = root
        self.home = root / "home"
        self.downloads = root / "downloads"
        self.library = root / "library"
        self.auto_add = root / "auto_add"
        for p in (self.home, self.downloads, self.library, self.auto_add):
            p.mkdir(parents=True, exist_ok=True)
        (self.home / "config.toml").write_text(
            f'[paths]\ndownloads = ["{self.downloads}"]\nlibrary = "{self.library}"\nauto_add = "{self.auto_add}"\n'
            f'evacuation = "{root / "evacuated"}"\n\n[convert]\nmin_free_gb = 0\n',
            encoding="utf-8",
        )
        self.cover = make_cover(root / "cover.jpg", "red")

    def config(self, **changes) -> config.Config:
        cfg = config.load(self.home)
        return config.Config(**{**cfg.__dict__, **changes}) if changes else cfg

    def download(
        self, folder: str, album_tag: str, artist: str, titles: list, numbers=None, discs=None, base_freq=300
    ) -> Path:
        """A download folder with store-style names and junk tags."""
        d = self.downloads / artist / folder
        for i, title in enumerate(titles):
            n = numbers[i] if numbers else i + 1
            extra = {"discnumber": discs[i]} if discs else {}
            make_flac(
                d / f"{n:02d}-{title}_{9000 + i}.flac",
                1 + 0.25 * i,
                base_freq + 40 * i,
                self.cover,
                title=title,
                artist=artist,
                album=album_tag,
                albumartist=artist,
                tracknumber=n,
                **extra,
            )
        return d

    def add_album(self, the_spec: dict, flac_dir: Path) -> None:
        catalog.add_spec(self.config(), the_spec, flac_dir)


@pytest.fixture
def env(tmp_path) -> Env:
    return Env(tmp_path)
