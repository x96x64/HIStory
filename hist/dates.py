"""Creation and modification dates of the library's folders and files, from dates.json.

An album entry sets the date on the album folder, its sub-folders and every .m4a/.m4v inside; an artist entry sets
it on the artist folder only. The commands are 'touch -t' and 'SetFile -d -m', run without a shell.
SetFile cannot set dates before 1970, so such entries are refused.
"""

import datetime
import json
import os
import re
from pathlib import Path

from hist import proc, state
from hist.errors import HistError

MEDIA = (".m4a", ".m4v")


class DatesError(HistError):
    code = "dates"


def entries(path: Path) -> list:
    """[{'kind': 'album'|'artist', 'path': 'Artist/Album', 'date': datetime}] in the order they are applied."""
    if not path.exists():
        return []
    doc = read_document(path)
    out = []
    for i, e in enumerate(doc["entries"], 1):
        if not isinstance(e, dict):
            raise DatesError(f"{path.name}: entry {i} is not an object")
        if e.get("kind") not in ("album", "artist"):
            raise DatesError(f"{path.name}: unknown kind {e.get('kind')!r} for {e.get('path')}")
        if not isinstance(e.get("path"), str) or not isinstance(e.get("date"), str):
            raise DatesError(f"{path.name}: entry {i} needs a text 'path' and a text 'date'")
        try:
            day = parse_date(e["date"])
        except DatesError as error:
            raise DatesError(f"{path.name}: {e['path']}: {error}") from None
        out.append({**e, "date": datetime.datetime.strptime(day, "%Y-%m-%d")})
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
        found += [Path(d) / f for f in sorted(files) if f.endswith(MEDIA)]  # case-sensitive, like find -name
    return found


def commands(entry: dict, root: Path) -> list:
    """touch and SetFile for the folder and, for an album, everything inside it (the folder is the first item)."""
    stamp = entry["date"].strftime("%Y%m%d%H%M.00")
    shown = entry["date"].strftime("%m/%d/%Y %H:%M:%S")
    every = [str(p) for p in items(entry, root)]
    return [["touch", "-t", stamp, *every], ["SetFile", "-d", shown, "-m", shown, *every]]


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
    return [
        e
        for e in all_entries
        if e in albums or (e["kind"] == "artist" and (e["path"] in artists or text in e["path"].casefold()))
    ]


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
    return (
        f"find {folder} {match} -exec touch -t {stamp} {{}} + && touch -t {stamp} {folder} && "
        f"find {folder} {match} -exec SetFile -d {shown} -m {shown} {{}} + && SetFile -d {shown} -m {shown} {folder}"
    )


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


# ----------------------------------------------------------- editing dates.json


def parse_date(text: str) -> str:
    """text as a valid YYYY-MM-DD date from 1970 on, else DatesError."""
    try:
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", text):
            raise ValueError
        day = datetime.datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise DatesError(f"'{text}' is not a date; write it as YYYY-MM-DD") from None
    if day.year < 1970:
        raise DatesError(f"'{text}': dates before 1970 cannot be set")
    return text


def kind_of(path: str, kind: str | None) -> str:
    """The kind of an entry: 'artist' for Artist, 'album' for Artist/Album; a given kind must agree."""
    parts = path.split("/")
    if len(parts) > 2 or any(p in ("", ".", "..") for p in parts):
        raise DatesError(f"'{path}' must be 'Artist' or 'Artist/Album', relative to the library")
    inferred = "artist" if len(parts) == 1 else "album"
    if kind is not None and kind != inferred:
        raise DatesError(
            f"'{path}' has {len(parts)} part{'s' * (len(parts) > 1)}, so it is an {inferred} entry, not {kind}"
        )
    return inferred


def read_document(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (ValueError, OSError) as error:
        raise DatesError(f"{path.name}: cannot be read: {error}") from None
    if not isinstance(doc, dict) or not isinstance(doc.setdefault("entries", []), list):
        raise DatesError(f"{path.name}: must be an object with a list 'entries'")
    return doc


def set_entry(path: Path, entry_path: str, date: str, kind: str | None, backup: state.Backup) -> dict:
    """Add or change the entry for entry_path; returns {"kind", "path", "date", "previous"} (previous may be None)."""
    date, kind = parse_date(date), kind_of(entry_path, kind)
    doc = read_document(path)
    found = next((e for e in doc["entries"] if e.get("kind") == kind and e.get("path") == entry_path), None)
    previous = found.get("date") if found else None
    if found is not None:
        found["date"] = date
    else:
        new = {"kind": kind, "path": entry_path, "date": date}
        first_album = next(
            (
                i
                for i, e in enumerate(doc["entries"])
                if kind == "artist" and e.get("kind") == "album" and e.get("path", "").split("/")[0] == entry_path
            ),
            len(doc["entries"]),
        )
        doc["entries"].insert(first_album, new)
    if previous != date:
        backup.keep(path)
        state.write_json(path, doc)
    return {"kind": kind, "path": entry_path, "date": date, "previous": previous}


def unset_entry(path: Path, entry_path: str, backup: state.Backup) -> list:
    """Remove every entry for entry_path; returns the removed entries, or raises DatesError when there is none."""
    doc = read_document(path)
    gone = [e for e in doc["entries"] if e.get("path") == entry_path]
    if not gone:
        raise DatesError(f"dates.json has no entry for '{entry_path}'")
    doc["entries"] = [e for e in doc["entries"] if e.get("path") != entry_path]
    backup.keep(path)
    state.write_json(path, doc)
    return gone
