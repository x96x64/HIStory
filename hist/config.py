"""Where the catalog lives and what config.toml says.

The catalog home is, in this order: the --home option, the HISTORY_HOME environment variable, or
~/Library/Application Support/HIStory. Paths in config.toml may start with '~'; relative paths are taken
relative to the home.
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from hist.errors import HistError

DEFAULT_HOME = "~/Library/Application Support/HIStory"
DEFAULT_LIBRARY = "~/Music/Music/Media.localized/Music"
DEFAULT_AUTO_ADD = "~/Music/Music/Media.localized/Automatically Add to Music.localized"
DEFAULT_EVACUATION = "~/Desktop/HIStory Evacuated"
# Folders where download services and their apps put albums by default on macOS. When [paths] downloads is empty or
# missing, every one of these that exists is scanned; a folder that appears later is picked up by the next scan.
# The whole ~/Downloads folder is not scanned, because it usually holds much more than music.
AUTO_DOWNLOADS = (
    "~/Music/mora",
    "~/Music/OTOTOY",
    "~/Music/Qobuz",
    "~/Music/Qobuz Downloads",
    "~/Music/e-onkyo music",
    "~/Music/HDtracks",
    "~/Music/7digital",
    "~/Music/Bandcamp",
    "~/Music/Downloads",
    "~/Downloads/Music",
    "~/Downloads/mora",
    "~/Downloads/OTOTOY",
    "~/Downloads/Qobuz",
    "~/Downloads/Bandcamp",
)

TEMPLATE = """\
# HIStory configuration. See docs/catalog-format.md for every key.

[paths]
# Folders that receive the downloaded albums (one sub-folder per album, at any depth). Leave the list empty to
# use the usual folders of download services (mora, OTOTOY, Qobuz, e-onkyo music, HDtracks, 7digital, Bandcamp
# and ~/Downloads/Music) that exist; 'hist doctor' shows which ones were found.
downloads = []
# The Music app's media folder and its 'Automatically Add to Music' folder.
library = "~/Music/Music/Media.localized/Music"
auto_add = "~/Music/Music/Media.localized/Automatically Add to Music.localized"
# Where 'hist evacuate' moves album folders out of the library.
evacuation = "~/Desktop/HIStory Evacuated"

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


class ConfigError(HistError):
    """config.toml is missing values or holds wrong ones."""

    code = "config"


def resolve_home(option: str | None = None) -> Path:
    raw = option or os.environ.get("HISTORY_HOME") or DEFAULT_HOME
    return Path(raw).expanduser()


@dataclass(frozen=True)
class Config:
    home: Path
    downloads: tuple = ()
    downloads_auto: bool = False
    library: Path = Path(DEFAULT_LIBRARY).expanduser()
    auto_add: Path = Path(DEFAULT_AUTO_ADD).expanduser()
    evacuation: Path = Path(DEFAULT_EVACUATION).expanduser()
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
    def present_downloads(self) -> list:
        """The download folders that exist now."""
        return [p for p in self.downloads if p.is_dir()]

    @property
    def sources(self) -> list:
        return list(self.downloads) + ([self.staging] if self.store_album else [])

    @property
    def store_library_copy(self) -> Path | None:
        return self.library / self.store_file if self.store_file else None

    @property
    def store_staged(self) -> Path | None:
        return self.staging / self.store_file if self.store_file else None


KEYS = {
    "paths": {"downloads", "library", "auto_add", "evacuation"},
    "convert": {"min_free_gb"},
    "store": {"album", "file"},
    "match": {"aliases", "renumber"},
}


def check_shape(data: dict) -> None:
    """Raise ConfigError for an unknown section or key, or a value of the wrong type."""
    for section, keys in data.items():
        if section not in KEYS:
            raise ConfigError(f"config.toml: unknown section [{section}]; known: {', '.join(sorted(KEYS))}")
        if not isinstance(keys, dict):
            raise ConfigError(f"config.toml: '{section}' must be a section [{section}]")
        for key in keys:
            if key not in KEYS[section]:
                raise ConfigError(
                    f"config.toml: unknown key '{key}' in [{section}]; known: {', '.join(sorted(KEYS[section]))}"
                )
    paths, store, match = (data.get(k, {}) for k in ("paths", "store", "match"))
    downloads = paths.get("downloads", [])
    if not isinstance(downloads, list) or not all(isinstance(d, str) for d in downloads):
        raise ConfigError("config.toml: [paths] downloads must be a list of folder names")
    for key in ("library", "auto_add", "evacuation"):
        if key in paths and not isinstance(paths[key], str):
            raise ConfigError(f"config.toml: [paths] {key} must be a text")
    free = data.get("convert", {}).get("min_free_gb", 10)
    if isinstance(free, bool) or not isinstance(free, (int, float)) or free < 0:
        raise ConfigError("config.toml: [convert] min_free_gb must be a number of at least 0")
    for key in ("album", "file"):
        if key in store and not isinstance(store[key], str):
            raise ConfigError(f"config.toml: [store] {key} must be a text")
    aliases = match.get("aliases", {})
    if not isinstance(aliases, dict) or not all(isinstance(v, str) for v in aliases.values()):
        raise ConfigError("config.toml: [match.aliases] must map album names to texts")
    renumber = match.get("renumber", {})
    if not isinstance(renumber, dict):
        raise ConfigError("config.toml: [match.renumber] must hold one table per album")
    for album, rule in renumber.items():
        if isinstance(rule, dict) and any(
            isinstance(rule.get(k), bool) or not isinstance(rule.get(k, 0), int) for k in ("disc", "offset")
        ):
            raise ConfigError(f"config.toml: [match.renumber.\"{album}\"] 'disc' and 'offset' must be integers")


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

    check_shape(data)
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
    auto = not downloads
    return Config(
        home=home,
        downloads=tuple(path(d) for d in (AUTO_DOWNLOADS if auto else downloads)),
        downloads_auto=auto,
        library=path(paths.get("library", DEFAULT_LIBRARY)),
        auto_add=path(paths.get("auto_add", DEFAULT_AUTO_ADD)),
        evacuation=path(paths.get("evacuation", DEFAULT_EVACUATION)),
        min_free_gb=float(data.get("convert", {}).get("min_free_gb", 10)),
        store_album=store.get("album"),
        store_file=store.get("file"),
        aliases=dict(match.get("aliases", {})),
        renumber=renumber,
    )
