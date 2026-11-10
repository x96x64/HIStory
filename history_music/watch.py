"""Watching the download folders and the library.

Downloads are converted as they complete (albums from specs are added to the catalog first). Albums you add to the
Music app are checked against the catalog and get their dates. The watch ends by itself when every album of the
catalog is converted and in the library, or, with --convert-only, when every album is converted.
"""
import time

from history_music import catalog, convert, library, matching, state, tags
from history_music.config import Config
from history_music.log import log
from history_music.runtime import Stopper

HEARTBEAT = 1500


def complete_download(config: Config, spec: dict):
    """The download folder of a spec album once every file has arrived, else None."""
    name = spec["album"]
    wanted = tags.norm(config.aliases.get(name, name))
    artist = tags.norm(spec["album_artist"])
    for folder in matching.scan(config.sources):
        if tags.similarity(folder.album, wanted, "substring") < 0.9:
            continue
        if tags.similarity(folder.artist, artist, "substring") < 0.9:
            continue
        flacs = [p for p in folder.files if p.suffix.lower() == ".flac"]
        if len(flacs) == len(spec["tracks"]) and not matching.check_ready(folder, "flac", deep=True):
            return folder
    return None


def wanted(only: str, name: str) -> bool:
    return not only or tags.norm(only) in tags.norm(name)


def add_ready_specs(config: Config, only: str) -> None:
    for path, spec in catalog.pending_specs(config):
        if not wanted(only, spec["album"]):
            continue
        folder = complete_download(config, spec)
        if folder is None:
            continue
        n = catalog.add_spec(config, spec, folder.path)
        log.info(f"Added {spec['album']} to the catalog from specs/{path.name} ({n} tracks)")
    for name in catalog.retire_applied_specs(config):
        log.info(f"Moved specs/{name} to state/history: its album is in the catalog")


def waiting_for(config: Config, only: str) -> list:
    """Albums still to be converted; an album already in the library counts as done."""
    names = convert.pending(config, only)
    names += [spec["album"] for _, spec in catalog.pending_specs(config) if wanted(only, spec["album"])]
    return names


def run(config: Config, options: convert.Options, stopper: Stopper, interval: float = 10,
        convert_only: bool = False) -> int:
    log.info("Watching " + ", ".join(str(p) for p in config.sources)
             + ("" if convert_only else f" and {config.library}") + " (Ctrl-C to stop)")
    follower = None if convert_only else library.Follower(config)
    last_beat, last_low, last_waiting = 0.0, (), None
    while True:
        stopper.check()
        try:
            add_ready_specs(config, options.only)
            result = convert.run_once(config, options, stopping=lambda: stopper.requested)
            if follower is not None:
                follower.look()
        except OSError as error:            # a folder was moved while it was scanned: look again
            log.debug(f"scan interrupted ({error}); looking again")
            with stopper.waiting():
                time.sleep(interval)
            continue
        stopper.check()
        if result.low_disk != last_low:
            for line in result.low_disk:
                log.warning(f"low disk space: {line}; skipped for now")
            last_low = result.low_disk
        names = waiting_for(config, options.only)
        absent = [] if follower is None else [n for n in follower.missing() if wanted(options.only, n)]
        if not names and not absent:
            log.info("All albums are converted." if follower is None else
                     "All albums are converted and in the library.")
            return 0
        now = (tuple(names), tuple(absent))
        if now != last_waiting or time.time() - last_beat > HEARTBEAT:
            if names:
                log.info(f"Waiting for {len(names)} download{'s' if len(names) != 1 else ''}; next: {names[0]}")
            if absent:
                ready = absent[0] in state.converted(config.state).names()
                log.info(f"Next album to add to the Music app: {absent[0]} "
                         + ("(converted, ready to add)" if ready else "(not converted yet)")
                         + f"; {len(absent)} not in the library yet")
            last_beat, last_waiting = time.time(), now
        with stopper.waiting():
            time.sleep(interval)
