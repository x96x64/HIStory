"""The Music app's entries of the store version of the album named in config.toml [store].

An entry counts as a store version only when its file still carries store purchase data. Before anything is
deleted, the cleaned copy in the staging folder must equal the catalog, carry no purchase data, and have the same
audio as every store file about to be removed.
"""

import time
from pathlib import Path

from hist import catalog, media, tags
from hist.config import Config
from hist.errors import HistError
from hist.log import log
from hist.music_app import MusicApp


class StoreError(HistError):
    pass


def cleaned_copy(config: Config) -> Path | None:
    folder = config.store_staged.parent
    files = sorted(folder.glob("*.m4a")) if folder.is_dir() else []
    return files[0] if len(files) == 1 else None


def run(config: Config, music: MusicApp, delete: bool) -> int:
    if not config.store_album:
        raise StoreError("config.toml has no [store] album")
    name = config.store_album
    rows = music.tracks(name)
    log.info(f"The Music app lists {len(rows)} entries of '{name}':")
    store = []
    for r in rows:
        path = Path(r["location"]) if r["location"] else None
        is_store = bool(path and path.exists() and media.has_store_protection(path))
        log.info(
            f"  id {r['id']}  {path.name if path else '(no file)'}  "
            f"{'store version' if is_store else 'no purchase data (kept)'}"
        )
        if is_store:
            store.append(r)
    if not delete:
        log.info(f"{len(store)} store-version entries; nothing was changed (use --delete to remove them)")
        return 0
    if not store:
        log.info("No store-version entries; nothing to delete.")
        return 0

    ref = [t for t in catalog.load(config) if tags.pick(t.tags, "album") == name]
    staged = cleaned_copy(config)
    if staged is None or not ref:
        raise StoreError(
            f"refusing to delete: no cleaned copy in {config.store_staged.parent} (run 'hist convert' first)"
        )
    cleaned = tags.read_tracks([(str(staged.parent), str(staged))])[0]
    if cleaned.tags != ref[0].tags or cleaned.blobs != ref[0].blobs or media.has_store_protection(staged):
        raise StoreError(
            "refusing to delete: the cleaned copy does not equal the catalog or still carries purchase data"
        )
    want = media.audio_packets(staged)
    differing = [Path(r["location"]).name for r in store if media.audio_packets(Path(r["location"])) != want]
    if differing:
        raise StoreError(f"refusing to delete: the audio of {', '.join(differing)} differs from the cleaned copy")

    ids = [r["id"] for r in store]
    music.delete_ids(ids)
    for _ in range(40):
        if not [r for r in music.tracks(name) if r["id"] in ids]:
            log.info(f"Deleted {len(ids)} store-version entries (their audio equals the cleaned copy).")
            return 0
        time.sleep(5)
    raise StoreError(
        "the entries are still listed after 200 seconds; the Music app may be showing a confirmation "
        "dialog. Answer it yourself, then run the command again"
    )
