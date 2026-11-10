"""Read-only verification of M4A files against the catalog."""
import collections
import os
import re
from pathlib import Path

from hist import catalog, media, tags
from hist.config import Config
from hist.log import log
from hist.music_app import MusicApp


def run(config: Config, roots: list, allow_missing: bool, decode: bool, music: MusicApp | None) -> int:
    saved = catalog.load(config)
    all_albums = catalog.albums(config)
    found = []
    for root in roots:
        if Path(root).is_dir():
            found += tags.read_tracks(tags.find_tracks([root], "m4a"))
    problems = []
    log.info(f"M4A files found: {len(found)}")

    ref = {(tags.pick(s.tags, "album"), s.number): s for s in saved}
    keys = [(tags.pick(t.tags, "album"), t.number) for t in found]
    missing = [k for k in ref if k not in set(keys)]
    dups = [k for k, v in collections.Counter(keys).items() if v > 1]
    unknown = [k for k in set(keys) if k not in ref]
    diff = [t for t, k in zip(found, keys) if k in ref and (t.tags != ref[k].tags or t.blobs != ref[k].blobs)]
    log.info(f"catalog tracks not found: {len(missing)}, found twice: {len(dups)}, not in the catalog: {len(unknown)}, "
             f"tags or cover differ: {len(diff)}")
    for t in diff[:10]:
        log.info(f"  differs: {t.path}")
    if (missing and not allow_missing) or dups or unknown or diff:
        problems.append("the set of tracks or their tags differ from the catalog")

    census = collections.Counter(k.split(":")[1] for t in found for k in list(t.tags) + list(t.blobs))
    comment = sum(1 for t in found if "ItemList:Comment" in t.tags)
    encoder = sum(1 for t in found if "ItemList:Encoder" in t.tags)
    nodisc = sum(1 for t in found if "ItemList:DiskNumber" not in t.tags)
    store = len(media.store_protected([t.path for t in found]))
    ids = [os.path.basename(t.path) for t in found if re.search(r"_\d{5,}\.m4a$", t.path)]
    log.info(f"Comment: {comment}, Encoder: {encoder}, without DiskNumber: {nodisc}, "
             f"store purchase data: {store}, names with a download id: {len(ids)}")
    if comment or encoder or nodisc or store or ids:
        problems.append("a file breaks the tag policy")

    other = collections.Counter()
    for atoms in tags.metadata_atoms_of([t.path for t in found]).values():
        for k in atoms:
            if k.split(":")[1] not in census:
                other[k] += 1
    log.info(f"unexpected metadata atoms: {dict(other) or 'none'}")
    if other:
        problems.append("unexpected metadata atoms")

    if decode:
        bad = [os.path.basename(t.path) for t in found
               if os.path.exists(t.path) and not media.decodes_cleanly(Path(t.path))]
        log.info(f"files that do not decode cleanly: {bad or 'none'}")
        if bad:
            problems.append("files do not decode cleanly")

    per = collections.Counter(tags.pick(t.tags, "album") for t in found)
    short = {a["name"]: (per.get(a["name"], 0), len(a["tracks"])) for a in all_albums
             if per.get(a["name"], 0) != len(a["tracks"])}
    log.info(f"albums whose track count differs: {short or 'none'}")
    if short and not allow_missing:
        problems.append("track counts differ")

    if music is not None:
        by, kinds = {}, collections.Counter()
        for album, kind, added in music.summary():
            kinds[kind] += 1
            by.setdefault(album, []).append(added)
        log.info(f"Music app kinds: {dict(kinds)}")
        purchased = sum(v for k, v in kinds.items() if "Purchased" in k)
        log.info(f"entries of a store version still listed: {purchased}")
        if purchased:
            problems.append("a store version is still listed ('hist store-entries')")
        listed = [a for a in all_albums if a["name"] in by]
        wrong = [a["name"] for a in listed if len(by[a["name"]]) != len(a["tracks"])]
        log.info(f"albums in the Music app with a wrong track count: {wrong or 'none'}")
        late = [(x["name"], y["name"]) for x, y in zip(listed, listed[1:]) if max(by[x["name"]]) > min(by[y["name"]])]
        log.info("albums were added in release order: " + ("yes" if not late else f"no, {late}"))
        if wrong or late:
            problems.append("the Music app's state differs from the catalog")

    if problems:
        log.info("Result: " + "; ".join(problems))
        return 1
    log.info("Result: all checks passed")
    return 0
