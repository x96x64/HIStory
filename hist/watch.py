"""Watching the download folders and the library.

Downloads are converted as they complete. Albums you add to the Music app are checked against the catalog and get
their dates. The watch ends by itself when every album of the catalog is converted and in the library, or, with
--convert-only, when every album is converted.
"""

import time

from hist import convert, library, state, tags
from hist.config import Config
from hist.log import log
from hist.runtime import Stopper

HEARTBEAT = 1500


def wanted(only: str, name: str) -> bool:
    return tags.matches_only(only, name)


def run(
    config: Config, options: convert.Options, stopper: Stopper, interval: float = 10, convert_only: bool = False
) -> int:
    log.info(
        "Watching "
        + (", ".join(str(p) for p in config.sources if p.is_dir()) or "no download folder yet")
        + (" (and the usual download folders as they appear)" if config.downloads_auto else "")
        + ("" if convert_only else f" and {config.library}")
        + " (Ctrl-C to stop)"
    )
    follower = None if convert_only else library.Follower(config)
    last_beat, last_low, last_waiting = 0.0, (), None
    while True:
        stopper.check()
        try:
            result = convert.run_once(config, options, stopping=lambda: stopper.requested)
            if follower is not None:
                follower.look()
        except OSError as error:  # a folder was moved while it was scanned: look again
            log.debug(f"scan interrupted ({error}); looking again")
            with stopper.waiting():
                time.sleep(interval)
            continue
        stopper.check()
        if result.low_disk != last_low:
            for line in result.low_disk:
                log.warning(f"low disk space: {line}; skipped for now")
            last_low = result.low_disk
        names = convert.pending(config, options.only)  # an album already in the library counts as done
        absent = [] if follower is None else [n for n in follower.missing() if wanted(options.only, n)]
        if not names and not absent:
            log.info(
                "All albums are converted." if follower is None else "All albums are converted and in the library."
            )
            return 0
        now = (tuple(names), tuple(absent))
        if now != last_waiting or time.time() - last_beat > HEARTBEAT:
            if names:
                log.info(f"Waiting for {len(names)} download{'s' if len(names) != 1 else ''}; next: {names[0]}")
            if absent:
                ready = absent[0] in state.converted(config.state).names()
                log.info(
                    f"Next album to add to the Music app: {absent[0]} "
                    + ("(converted, ready to add)" if ready else "(not converted yet)")
                    + f"; {len(absent)} not in the library yet"
                )
            last_beat, last_waiting = time.time(), now
        with stopper.waiting():
            time.sleep(interval)
