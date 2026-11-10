"""Writing the catalog's tags back into existing M4A files (for files converted before a catalog change)."""
import time
from collections import defaultdict
from pathlib import Path

from history_music import catalog, matching, state, tags
from history_music.config import Config
from history_music.log import log
from history_music.tags import Match


def snapshot(config: Config, found: list) -> Path:
    """Save the current tags of the files before writing, in the catalog's format."""
    base = config.state / "snapshots" / time.strftime("retag-%Y%m%d-%H%M%S")
    dest, n = base, 2
    while dest.exists():
        dest = base.with_name(f"{base.name}-{n}")
        n += 1
    records = [{"file": t.path, "tags": t.tags, "blobs": t.blobs}
               for t in tags.read_tracks(found, dest / "covers")]
    state.write_json(dest / "tracks.json", {"format": catalog.FORMAT, "tracks": records})
    return dest


def run(config: Config, roots: list, apply: bool, fields: str, prune: bool, verbose: bool) -> int:
    saved = catalog.load(config)
    found = tags.find_tracks(roots, "m4a")
    if not found:
        log.info("No M4A files found.")
        return 0
    current = tags.read_tracks(found)
    pairs, unmatched, number_only = matching.pair_tracks(saved, current, "similarity", 0.9, 0.85, True)
    wanted = {f.strip().lower() for f in fields.split(",") if f.strip()} if fields else set()
    matches, identical, skipped = [], 0, defaultdict(int)
    for ci, si in pairs:
        sets, blob_sets, deletes, skip = tags.diff_tracks(current[ci], saved[si], wanted, prune)
        for tag in skip:
            skipped[tags.tag_name(tag)] += 1
        if sets or blob_sets or deletes:
            matches.append(Match(current[ci], saved[si], sets, blob_sets, deletes, (ci, si) in number_only))
        else:
            identical += 1
    log.info(f"{len(current)} files: {len(pairs)} matched ({len(number_only)} without a similar title), "
             f"{identical} already equal, {len(matches)} to change, {len(unmatched)} without a match")
    for m in matches:
        log.info(f"~ {m.current.path}" + ("  (matched by number or elimination)" if m.by_number else ""))
        for tag, value in m.sets.items():
            log.info(f"    {tag}: {m.current.tags.get(tag, '<none>')} -> {value}")
        for tag in m.blob_sets:
            log.info(f"    {tag}: cover replaced")
        for tag in m.deletes:
            log.info(f"    {tag}: removed")
    if unmatched and verbose:
        for c, reason in unmatched:
            log.info(f"? {c.path}: {reason}")
    if skipped:
        log.info("not writable by exiftool and left alone: " + ", ".join(f"{k} ({v})" for k, v in sorted(skipped.items())))
    if not apply:
        if matches:
            log.info("Nothing was written; add --apply to write these changes.")
        return 0
    if not matches:
        return 0
    dest = snapshot(config, [(m.current.root, m.current.path) for m in matches])
    log.info(f"Saved the current tags to {dest}")
    failed = 0
    for m in matches:
        error = tags.write_match(m, config.covers)
        if error is None:
            after = tags.read_tracks([(m.current.root, m.current.path)])
            if after:
                sets, blob_sets, deletes, _ = tags.diff_tracks(after[0], m.saved, wanted, prune)
                if sets or blob_sets or deletes:
                    error = "tags differ from the catalog after writing"
        if error:
            failed += 1
            log.error(f"{m.current.path}: {error}")
    log.info(f"Wrote {len(matches) - failed} files, {failed} failed. Writing changed the files' dates: "
             "run 'hist dates apply' for albums in the library.")
    return 1 if failed else 0
