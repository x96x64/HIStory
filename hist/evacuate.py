"""Moving album folders out of the library and removing their entries, so that they can be added again.

Folders are moved first, then the entries are deleted: while a file exists, deleting its entry can raise a
confirmation dialog; without the file it does not. Nothing is deleted from disk. Add the albums again from that
folder in the Music app, one at a time, while 'hist watch' runs.
"""

import os
import time
from pathlib import Path

from hist import catalog, state, tags
from hist.config import Config
from hist.errors import HistError
from hist.log import log
from hist.music_app import MusicApp


class EvacuateError(HistError):
    pass


def plan(config: Config, music: MusicApp, only: str) -> list:
    items = []
    for order, album in enumerate(catalog.albums(config), 1):
        if only and tags.norm(only) not in tags.norm(album["name"]):
            continue
        rows = music.tracks(album["name"])
        if not rows:
            continue
        folders = {str(Path(r["location"]).parent) for r in rows if r["location"]}
        items.append({"order": order, "album": album["name"], "tracks": len(rows), "folders": sorted(folders)})
    return items


def run(config: Config, music: MusicApp, only: str, dry_run: bool) -> int:
    items = plan(config, music, only)
    if not items:
        log.info("No album of the catalog is listed in the Music app; nothing to do.")
        return 0
    failed = 0
    for it in items:
        if len(it["folders"]) != 1:
            log.warning(f"{it['album']} is spread over {len(it['folders'])} folders; skipped")
            failed += 1
            continue
        src = Path(it["folders"][0])
        dst = config.evacuation / f"{it['order']:02d} {src.name}"
        if dry_run:
            log.info(f"Would move {src} to {dst} and remove {it['tracks']} entries of {it['album']}")
            continue
        config.evacuation.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            log.warning(f"{dst} already exists; {it['album']} skipped")
            failed += 1
            continue
        os.rename(src, dst)
        music.delete_album(it["album"])
        for _ in range(45):
            if not music.tracks(it["album"]):
                state.added(config.state).remove(it["album"])
                log.info(f"Moved {it['album']} ({it['tracks']} tracks) to {dst}")
                break
            time.sleep(2)
        else:
            raise EvacuateError(
                f"the entries of {it['album']} are still listed; the Music app may be showing a "
                f"dialog. Answer it yourself. The files are safe in {dst}"
            )
    if not dry_run:
        log.info(
            f"Add the albums again from {config.evacuation} in the Music app, one at a time, while 'hist watch' runs."
        )
    return 1 if failed else 0
