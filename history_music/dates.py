"""Creation and modification dates of the library's folders and files, from dates.json.

An album entry sets the date on the album folder, its sub-folders and every .m4a/.m4v inside; an artist entry sets
it on the artist folder only. The commands are 'touch -t' and 'SetFile -d -m', run without a shell.
SetFile cannot set dates before 1970, so such entries are refused.
"""
import datetime
import json
import os
from pathlib import Path

from history_music import proc

MEDIA = (".m4a", ".m4v")


class DatesError(Exception):
    pass


def entries(path: Path) -> list:
    """[{'kind': 'album'|'artist', 'path': 'Artist/Album', 'date': datetime}] in the order they are applied."""
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for e in doc.get("entries", []):
        if e.get("kind") not in ("album", "artist"):
            raise DatesError(f"{path.name}: unknown kind {e.get('kind')!r} for {e.get('path')}")
        out.append({**e, "date": datetime.datetime.strptime(e["date"], "%Y-%m-%d")})
    return out


def items(entry: dict, root: Path) -> list:
    """The folder first, then (album) its sub-folders and media files."""
    folder = root / entry["path"]
    if entry["kind"] == "artist":
        return [folder]
    found = [folder]
    for d, subdirs, files in os.walk(folder):
        subdirs.sort()
        found += [Path(d) / s for s in subdirs]
        found += [Path(d) / f for f in sorted(files) if f.endswith(MEDIA)]     # case-sensitive, like find -name
    return found


def commands(entry: dict, root: Path) -> list:
    folder = root / entry["path"]
    stamp = entry["date"].strftime("%Y%m%d%H%M.00")
    shown = entry["date"].strftime("%m/%d/%Y %H:%M:%S")
    every = [str(p) for p in items(entry, root)]
    if entry["kind"] == "artist":
        return [["touch", "-t", stamp, str(folder)], ["SetFile", "-d", shown, "-m", shown, str(folder)]]
    return [["touch", "-t", stamp, *every], ["touch", "-t", stamp, str(folder)],
            ["SetFile", "-d", shown, "-m", shown, *every], ["SetFile", "-d", shown, "-m", shown, str(folder)]]


def apply(entry: dict, root: Path) -> None:
    if entry["date"].year < 1970:
        raise DatesError(f"{entry['path']}: dates before 1970 cannot be set ({entry['date']:%Y-%m-%d})")
    for cmd in commands(entry, root):
        done = proc.run(cmd, text=True)
        if done.returncode:
            raise DatesError(f"{entry['path']}: {cmd[0]} failed: {done.stderr.strip()[-200:]}")


def check(entry: dict, root: Path) -> list:
    """Items whose creation or modification date is not the entry's date (empty when all agree)."""
    wrong = []
    for item in items(entry, root):
        st = os.stat(item)
        birth = datetime.datetime.fromtimestamp(st.st_birthtime)
        mod = datetime.datetime.fromtimestamp(st.st_mtime)
        if birth != entry["date"] or mod != entry["date"]:
            wrong.append((item, birth, mod))
    return wrong


def select(all_entries: list, only: str) -> list:
    """Entries whose path contains `only`; the artist entry of each matching album comes along, before it."""
    if not only:
        return all_entries
    text = only.casefold()
    albums = [e for e in all_entries if e["kind"] == "album" and text in e["path"].casefold()]
    artists = {e["path"].split("/")[0] for e in albums}
    return [e for e in all_entries if e in albums or
            (e["kind"] == "artist" and (e["path"] in artists or text in e["path"].casefold()))]


def for_album(rel: str, all_entries: list):
    """(artist entry, album entry) for 'Artist/Album'; either may be None."""
    artist = next((e for e in all_entries if e["kind"] == "artist" and e["path"] == rel.split("/")[0]), None)
    album = next((e for e in all_entries if e["kind"] == "album" and e["path"] == rel), None)
    return artist, album


def shell_line(entry: dict, root: Path) -> str:
    """The same work as one shell command line."""
    def q(text: str) -> str:
        return "'" + text.replace("'", "'\\''") + "'"
    folder = q(str(root / entry["path"]))
    stamp = entry["date"].strftime("%Y%m%d%H%M.00")
    shown = '"' + entry["date"].strftime("%m/%d/%Y %H:%M:%S") + '"'
    if entry["kind"] == "artist":
        return f"[ -d {folder} ] && touch -t {stamp} {folder} && SetFile -d {shown} -m {shown} {folder}"
    match = r'\( -type d -o -name "*.m4a" -o -name "*.m4v" \)'
    return (f"find {folder} {match} -exec touch -t {stamp} {{}} + && touch -t {stamp} {folder} && "
            f"find {folder} {match} -exec SetFile -d {shown} -m {shown} {{}} + && SetFile -d {shown} -m {shown} {folder}")


def apply_album(rel: str, all_entries: list, root: Path) -> str:
    """Apply the artist entry, then the album entry, of one album folder; returns a short outcome."""
    artist, album = for_album(rel, all_entries)
    if album is None:
        return "no dates entry"
    for entry in (artist, album):
        if entry is not None:
            apply(entry, root)
    wrong = check(album, root) + (check(artist, root) if artist else [])
    if wrong:
        raise DatesError(f"{rel}: {len(wrong)} items do not carry the date after setting it")
    return "dates set"
