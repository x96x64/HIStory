"""Finding album folders and pairing their files with the catalog's tracks."""
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from hist import media
from hist.tags import Track, first, pick, read_tracks, similarity

SOURCE_EXT = (".flac", ".m4a")
PARTIAL_SUFFIXES = (".part", ".crdownload", ".download", ".tmp", ".partial")
SETTLE_SECONDS = 10


def albums(tracks: list[Track]) -> list[dict]:
    """The catalog's albums, oldest release first (then by name)."""
    groups = defaultdict(list)
    for t in tracks:
        groups[(t.album, t.artist)].append(t)
    out = []
    for key, members in groups.items():
        dates = [d for d in (first(t.tags.get("ItemList:ContentCreateDate"))[:10].replace(":", "-")
                             for t in members) if re.fullmatch(r"\d{4}-\d\d-\d\d", d)]
        out.append({"key": key, "name": pick(members[0].tags, "album"), "tracks": members,
                    "release": min(dates) if dates else "9999-12-31"})
    return sorted(out, key=lambda a: (a["release"], a["name"]))


def numbered(tracks: list[Track], indexes: list[int]) -> bool:
    numbers = [tracks[i].number for i in indexes]
    return None not in numbers and len(set(numbers)) == len(numbers)


def pair_tracks(saved: list[Track], current: list[Track], mode: str, threshold: float,
                title_threshold: float, by_number: bool = True):
    """Assign each current file to at most one saved track.

    Returns (pairs, unmatched with reason, pairs made without a similar title). Two fallbacks exist, both only for
    an album whose files and saved tracks are equally many: a distinct disc/track number may pair a translated or
    reworded title, and when exactly one file and one saved track are left over after everything else is paired,
    they belong together. Titles that contain one another (versions of one song) can still be paired wrongly;
    'hist convert --dry-run' shows the pairing with durations before anything is written.
    """
    saved_by_album, current_by_album = defaultdict(list), defaultdict(list)
    for i, t in enumerate(saved):
        saved_by_album[(t.album, t.artist)].append(i)
    for i, t in enumerate(current):
        current_by_album[(t.album, t.artist)].append(i)

    candidates, album_known, number_only, groups = [], set(), set(), []
    for ckey, cidx in current_by_album.items():
        if not (ckey[0] and ckey[1]):
            continue
        for skey, sidx in saved_by_album.items():
            if not (skey[0] and skey[1]):
                continue
            a = similarity(ckey[0], skey[0], mode)
            r = similarity(ckey[1], skey[1], mode) if a >= threshold else 0.0
            if a < threshold or r < threshold:
                continue
            album_known.update(cidx)
            use_numbers = (by_number and len(cidx) == len(sidx)
                           and numbered(current, cidx) and numbered(saved, sidx))
            if by_number and len(cidx) == len(sidx):
                groups.append((cidx, sidx))
            for ci in cidx:
                c = current[ci]
                for si in sidx:
                    s = saved[si]
                    ts = similarity(c.title, s.title, mode)
                    same_number = c.number is not None and c.number == s.number
                    if ts >= title_threshold or (same_number and ts >= 0.5):
                        key = (round(a + r, 6), round(ts, 6), same_number, c.path == s.path)
                        candidates.append((key, ci, si))
                    elif use_numbers and same_number:
                        key = (round(a + r, 6), round(ts, 6), True, c.path == s.path)
                        candidates.append((key, ci, si))
                        number_only.add((ci, si))

    candidates.sort(key=lambda c: c[0], reverse=True)
    used_c, used_s, pairs = set(), set(), []
    for _, ci, si in candidates:
        if ci not in used_c and si not in used_s:
            used_c.add(ci)
            used_s.add(si)
            pairs.append((ci, si))
    number_only &= set(pairs)
    for cidx, sidx in groups:
        left_c = [ci for ci in cidx if ci not in used_c]
        left_s = [si for si in sidx if si not in used_s]
        if len(left_c) == 1 and len(left_s) == 1:
            used_c.add(left_c[0])
            used_s.add(left_s[0])
            pairs.append((left_c[0], left_s[0]))
            number_only.add((left_c[0], left_s[0]))
    unmatched = []
    for ci, c in enumerate(current):
        if ci not in used_c:
            reason = ("no track of a similar title in the matching catalog album" if ci in album_known
                      else "no catalog album resembles this album and artist")
            unmatched.append((c, reason))
    return pairs, unmatched, number_only


@dataclass
class Folder:
    path: Path
    files: list
    partial: list
    album: str
    artist: str

    @property
    def count(self) -> int:
        # a folder that holds FLAC files is counted by them: M4A files left from an earlier conversion do not count
        flacs = [f for f in self.files if f.suffix.lower() == ".flac"]
        return len({f.stem for f in (flacs or self.files)})

    @property
    def has_flac(self) -> bool:
        return any(f.suffix.lower() == ".flac" for f in self.files)


def find_folders(root: Path) -> list[Folder]:
    folders = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        names = [n for n in sorted(filenames) if not n.startswith(".")]
        files = [Path(dirpath) / n for n in names if n.lower().endswith(SOURCE_EXT)]
        if not files:
            continue
        try:
            probe = read_tracks([(str(root), str(files[0]))])
        except OSError:          # the folder was moved or deleted while it was being scanned
            continue
        if not probe:
            continue
        partial = [Path(dirpath) / n for n in names if n.lower().endswith(PARTIAL_SUFFIXES)]
        folders.append(Folder(Path(dirpath), files, partial, probe[0].album, probe[0].artist))
    return folders


def scan(roots) -> list[Folder]:
    return [f for root in roots if Path(root).is_dir() for f in find_folders(Path(root))]


def pick_folder(album: dict, folders: list[Folder], threshold: float):
    """The downloaded folder for this album: names match partially and the track count is equal."""
    near = []
    for f in folders:
        a = similarity(f.album, album["key"][0], "substring")
        r = similarity(f.artist, album["key"][1], "substring")
        if a >= threshold and r >= threshold:
            near.append((a + r, f))
    near.sort(key=lambda x: -x[0])
    for _, f in near:
        if f.count == len(album["tracks"]):
            return f, None
    if near:
        f = near[0][1]
        return None, f"{f.path} holds {f.count} of {len(album['tracks'])} tracks (still downloading?)"
    return None, "not downloaded yet"


def check_ready(folder: Folder, mode: str, deep: bool):
    """Problems that keep a folder from being processed now (an empty list when it is ready)."""
    flacs = [p for p in folder.files if p.suffix.lower() == ".flac"]
    m4as = [p for p in folder.files if p.suffix.lower() == ".m4a"]
    problems = []
    if folder.partial:
        problems.append("unfinished download files: " + ", ".join(p.name for p in folder.partial))
    if mode == "flac" and not flacs:
        problems.append("no FLAC files to convert")
    sources = flacs if mode == "flac" else m4as
    now = time.time()
    young = [p for p in sources if now - p.stat().st_mtime < SETTLE_SECONDS]
    if young:
        problems.append(f"{len(young)} files changed within the last {SETTLE_SECONDS} seconds (still downloading?)")
    if deep and not problems:
        sizes = {p: p.stat().st_size for p in sources}
        time.sleep(2)
        if any(p.stat().st_size != sizes[p] for p in sources):
            problems.append("file sizes are still changing")
        else:
            bad = [p.name for p in sources if not media.decodes_cleanly(p)]
            if bad:
                problems.append("these files do not decode cleanly: " + ", ".join(bad))
    return problems
