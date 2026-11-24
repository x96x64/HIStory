"""Albums you add to the Music app: noticing them, checking them, and setting their dates.

hist never adds anything to the Music app. When an album you added appears in the library folder and its files
have stopped changing, its tags are compared with the catalog, the dates of its artist folder and album folder are
set from dates.json, and the album is recorded as added. An album that leaves the library is forgotten, so it is
checked and dated again when it comes back.
"""

import time
from pathlib import Path

from hist import catalog, dates, state, tags
from hist.config import Config
from hist.log import log

SETTLE_SECONDS = 10


def album_folders(library: Path) -> dict:
    """{'Artist/Album': [media files]} for every album folder of the library that holds .m4a or .m4v files."""
    found = {}
    if not library.is_dir():
        return found
    for artist in sorted(p for p in library.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for album in sorted(p for p in artist.iterdir() if p.is_dir() and not p.name.startswith(".")):
            files = sorted(f for f in album.iterdir() if f.suffix.lower() in (".m4a", ".m4v"))
            if files:
                found[f"{artist.name}/{album.name}"] = files
    return found


def signature(files: list) -> list:
    return sorted((f.name, f.stat().st_size) for f in files)


def differing(album: dict, found: list) -> list:
    by_number = {s.number: s for s in album["tracks"]}
    return [
        Path(t.path).name
        for t in found
        if t.number not in by_number or t.tags != by_number[t.number].tags or t.blobs != by_number[t.number].blobs
    ]


class Follower:
    """Keeps track of album folders in the library between looks."""

    def __init__(self, config: Config):
        self.config = config
        self.seen = {}  # 'Artist/Album' -> (signature, time it last changed)
        self.told = set()

    def look(self) -> int:
        """Check and date every settled album that is not recorded yet; returns how many were dated."""
        cfg = self.config
        progress = state.added(cfg.state)
        recorded = progress.load()
        folders = album_folders(cfg.library)
        all_albums = catalog.albums(cfg)
        by_name = {a["name"]: a for a in all_albums}
        by_key = {a["key"]: a for a in all_albums}

        def folder_of(name: str, info: dict) -> str | None:
            if info.get("folder"):
                return info["folder"]
            album = by_name.get(name)  # records of earlier builds hold no folder
            return str(Path(album["tracks"][0].path).parent.relative_to(cfg.library)) if album else None

        for name, info in list(recorded.items()):  # an album that left the library is forgotten
            folder = folder_of(name, info)
            if folder and folder not in folders:
                progress.remove(name)
                log.info(f"{name} is no longer in the library; it will be checked again when it is added")
        recorded = progress.load()
        done_folders = {folder_of(name, info) for name, info in recorded.items()}
        handled = 0
        for rel, files in folders.items():
            if rel in done_folders:
                continue
            sig = signature(files)
            before = self.seen.get(rel)
            if before is None or before[0] != sig:
                self.seen[rel] = (sig, time.time())
                continue
            if time.time() - before[1] < SETTLE_SECONDS:
                continue
            found = tags.read_tracks([(str(cfg.library / rel), str(f)) for f in files if f.suffix.lower() == ".m4a"])
            keys = {(t.album, t.artist) for t in found}
            album = by_key.get(keys.pop()) if len(keys) == 1 else None
            if album is None or album["name"] in recorded:
                if rel not in self.told:
                    log.debug(f"{rel} is not an album of the catalog (or already recorded); left alone")
                    self.told.add(rel)
                continue
            if len(found) < len(album["tracks"]):
                continue  # still being added
            bad = differing(album, found)
            if bad or len(found) != len(album["tracks"]):
                if rel not in self.told:
                    log.warning(
                        f"{album['name']}: {len(bad) or len(found)} files in the library differ from the "
                        f"catalog (e.g. {bad[0] if bad else 'track count'}); dates were not set"
                    )
                    self.told.add(rel)
                continue
            outcome = dates.apply_album(rel, dates.entries(cfg.dates_file), cfg.library)
            progress.add(album["name"], folder=rel, tracks=len(found), dates=outcome)
            log.info(f"{album['name']} is in the library ({len(found)} tracks, {outcome})")
            if outcome == "no dates entry":
                log.warning(f"dates.json has no entry for {rel}; its dates were not set")
            handled += 1
        return handled

    def missing(self) -> list:
        """Catalog albums not recorded as added yet, oldest release first."""
        recorded = state.added(self.config.state).names()
        return [a["name"] for a in catalog.albums(self.config) if a["name"] not in recorded]
