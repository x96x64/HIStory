"""Where the catalog lives and what config.toml says.

The catalog home is, in this order: the --home option, the HISTORY_HOME environment variable, or
~/Library/Application Support/HIStory. Paths in config.toml may start with '~'; relative paths are taken
relative to the home.
"""
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_HOME = "~/Library/Application Support/HIStory"
DEFAULT_LIBRARY = "~/Music/Music/Media.localized/Music"
DEFAULT_AUTO_ADD = "~/Music/Music/Media.localized/Automatically Add to Music.localized"

TEMPLATE = """\
# HIStory configuration. See docs/catalog-format.md for every key.

[paths]
# Folders that receive the downloaded albums (one sub-folder per album, at any depth).
downloads = []
# The Music app's media folder and its 'Automatically Add to Music' folder.
library = "~/Music/Music/Media.localized/Music"
auto_add = "~/Music/Music/Media.localized/Automatically Add to Music.localized"
# Where 'hist evacuate' moves album folders out of the library.
evacuation = "~/Music/HIStory Evacuated"

[convert]
# An album is not converted unless this much space (GB) stays free after the work it needs.
min_free_gb = 10

# An album bought in the Music app's store instead of downloaded as FLAC (optional).
# [store]
# album = "Album Name"
# file = "Artist/Album Name/01 Song.m4a"   # relative to the library

# A download folder whose album name differs from the catalog's.
# [match.aliases]
# "Album Name in the Catalog" = "Album Name of the Download"

# A download that is one disc of a larger set, numbered on from the earlier discs.
# [match.renumber."Album Name in the Catalog"]
# disc = 1
# offset = 88
"""


class ConfigError(Exception):
    """config.toml is missing values or holds wrong ones."""


def resolve_home(option: str | None = None) -> Path:
    raw = option or os.environ.get("HISTORY_HOME") or DEFAULT_HOME
    return Path(raw).expanduser()


@dataclass(frozen=True)
class Config:
    home: Path
    downloads: tuple = ()
    library: Path = Path(DEFAULT_LIBRARY).expanduser()
    auto_add: Path = Path(DEFAULT_AUTO_ADD).expanduser()
    evacuation: Path = Path("~/Music/HIStory Evacuated").expanduser()
    min_free_gb: float = 10.0
    store_album: str | None = None
    store_file: str | None = None
    aliases: dict = field(default_factory=dict)
    renumber: dict = field(default_factory=dict)

    @property
    def config_file(self) -> Path:
        return self.home / "config.toml"

    @property
    def tracks_file(self) -> Path:
        return self.home / "tracks.json"

    @property
    def covers(self) -> Path:
        return self.home / "covers"

    @property
    def specs(self) -> Path:
        return self.home / "specs"

    @property
    def dates_file(self) -> Path:
        return self.home / "dates.json"

    @property
    def state(self) -> Path:
        return self.home / "state"

    @property
    def staging(self) -> Path:
        """Where the store file is copied to be cleaned; it is scanned like a download folder."""
        return self.state / "staging"

    @property
    def sources(self) -> list:
        return list(self.downloads) + ([self.staging] if self.store_album else [])

    @property
    def store_library_copy(self) -> Path | None:
        return self.library / self.store_file if self.store_file else None

    @property
    def store_staged(self) -> Path | None:
        return self.staging / self.store_file if self.store_file else None


def load(home: Path, downloads_override=None) -> Config:
    """Read config.toml in home (a missing file gives the defaults)."""
    data = {}
    if (home / "config.toml").exists():
        try:
            data = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            raise ConfigError(f"{home / 'config.toml'}: {error}") from None

    def path(value) -> Path:
        p = Path(str(value)).expanduser()
        return p if p.is_absolute() else home / p

    paths = data.get("paths", {})
    store = data.get("store", {})
    match = data.get("match", {})
    if bool(store.get("album")) != bool(store.get("file")):
        raise ConfigError("[store] needs both 'album' and 'file'")
    renumber = {}
    for album, rule in match.get("renumber", {}).items():
        if not isinstance(rule, dict) or not {"disc", "offset"} <= set(rule):
            raise ConfigError(f"[match.renumber.\"{album}\"] needs 'disc' and 'offset'")
        renumber[album] = {"disc": int(rule["disc"]), "offset": int(rule["offset"])}
    downloads = downloads_override if downloads_override else paths.get("downloads", [])
    return Config(
        home=home,
        downloads=tuple(path(d) for d in downloads),
        library=path(paths.get("library", DEFAULT_LIBRARY)),
        auto_add=path(paths.get("auto_add", DEFAULT_AUTO_ADD)),
        evacuation=path(paths.get("evacuation", "~/Music/HIStory Evacuated")),
        min_free_gb=float(data.get("convert", {}).get("min_free_gb", 10)),
        store_album=store.get("album"),
        store_file=store.get("file"),
        aliases=dict(match.get("aliases", {})),
        renumber=renumber,
    )
