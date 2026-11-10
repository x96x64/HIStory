"""Reading and writing tags with exiftool, and comparing names.

Tag names carry their exiftool group, for example ItemList:Title. Binary values (cover art) are kept as the
SHA-256 of their bytes.
"""
import base64
import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from hist import proc
from hist.log import log

TAG_GROUPS = ("ItemList", "UserData", "Keys", "ID3", "Vorbis", "APE", "XMP")
STRIP_GROUPS = ("ItemList", "UserData", "Keys", "XMP")
CHUNK = 40
MIN_SUBSTRING = 3

ALIASES = {
    "album": ("Album",),
    "albumartist": ("AlbumArtist", "Albumartist", "Band"),
    "artist": ("Artist",),
    "title": ("Title",),
    "track": ("TrackNumber", "Tracknumber", "Track"),
    "disc": ("DiskNumber", "DiscNumber", "Discnumber", "PartOfSet"),
}


def exiftool() -> str:
    return proc.which("exiftool")


def norm(text) -> str:
    """Lower-case, width-fold, drop accents on Latin letters, punctuation and a leading article."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    kept = []
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.combining(ch) and kept and ord(kept[-1]) < 0x250:
            continue
        kept.append(ch)
    text = unicodedata.normalize("NFC", "".join(kept))
    text = re.sub(r"[\W_]+", " ", text).strip()
    return re.sub(r"^(the|a|an) ", "", text)


@lru_cache(maxsize=None)
def similarity(a: str, b: str, mode: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if mode == "substring":
        short, long_ = sorted((a, b), key=len)
        if len(short) >= MIN_SUBSTRING and f" {short} " in f" {long_} ":
            return 0.97 + 0.02 * SequenceMatcher(None, a, b).ratio()
    return SequenceMatcher(None, a, b).ratio()


def first(value) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    return "" if value is None else str(value)


def pick(tags: dict, name: str) -> str:
    wanted = {a.lower() for a in ALIASES[name]}
    for tag, value in tags.items():
        if tag.split(":", 1)[-1].lower() in wanted and first(value):
            return first(value)
    return ""


def leading_int(text: str):
    m = re.match(r"\s*(\d+)", text)
    return int(m.group(1)) if m else None


@dataclass
class Track:
    path: str
    root: str
    tags: dict
    blobs: dict
    album: str = field(init=False)
    artist: str = field(init=False)
    title: str = field(init=False)
    number: tuple | None = field(init=False)

    def __post_init__(self):
        self.album = norm(pick(self.tags, "album"))
        self.artist = norm(pick(self.tags, "albumartist") or pick(self.tags, "artist"))
        self.title = norm(pick(self.tags, "title"))
        track = leading_int(pick(self.tags, "track"))
        disc = leading_int(pick(self.tags, "disc")) or 1
        self.number = None if track is None else (disc, track)


def find_tracks(roots, exts: str):
    """(root, path) of every audio file with one of the extensions under the roots, without duplicates."""
    wanted = {"." + e.strip().lstrip(".").lower() for e in exts.split(",") if e.strip()}
    seen, found = set(), []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                path = Path(dirpath) / name
                if name.startswith(".") or path.suffix.lower() not in wanted:
                    continue
                real = os.path.realpath(path)
                if real not in seen:
                    seen.add(real)
                    found.append((str(root), str(path)))
    return found


def read_tracks(found, blob_dir: Path | None = None) -> list[Track]:
    """Read every tag of the given (root, path) pairs; binary values go to blob_dir by SHA-256."""
    tracks = []
    root_of = dict((path, root) for root, path in found)
    paths = [path for _, path in found]
    for i in range(0, len(paths), CHUNK):
        chunk = paths[i:i + CHUNK]
        done = proc.run([exiftool(), "-q", "-j", "-b", "-G1", "-charset", "filename=UTF8",
                         *(f"-{g}:all" for g in TAG_GROUPS), *chunk])
        if done.stderr.strip():
            log.warning(done.stderr.decode("utf-8", "replace").strip())
        text = done.stdout.decode("utf-8")
        items = json.loads(text) if text.strip() else []
        got = set()
        for item in items:
            path = item.pop("SourceFile")
            got.add(path)
            tags, blobs = {}, {}
            for tag, value in item.items():
                if tag.startswith(("ExifTool:", "System:")):
                    continue
                values = value if isinstance(value, list) else [value]
                if any(isinstance(v, str) and v.startswith("base64:") for v in values):
                    blobs[tag] = [store_blob(v[7:], blob_dir) for v in values]
                else:
                    tags[tag] = value
            tracks.append(Track(path, root_of[path], tags, blobs))
        for path in chunk:
            if path not in got:
                log.warning(f"no tags could be read from {path}")
    return tracks


def store_blob(encoded: str, blob_dir: Path | None) -> str:
    raw = base64.b64decode(encoded)
    digest = hashlib.sha256(raw).hexdigest()
    if blob_dir is not None:
        blob_dir.mkdir(parents=True, exist_ok=True)
        target = blob_dir / digest
        if not target.exists():
            target.write_bytes(raw)
    return digest


def metadata_atoms(path: str) -> set:
    """Names of every metadata atom of an M4A file, unknown ones included."""
    return metadata_atoms_of([path]).get(path, set())


def metadata_atoms_of(paths: list) -> dict:
    """{path: names of every metadata atom}, reading CHUNK files per exiftool run."""
    found = {}
    for i in range(0, len(paths), CHUNK):
        out = proc.run([exiftool(), "-q", "-a", "-u", "-G1", "-s3", "-j", "-charset", "filename=UTF8",
                        "-ItemList:all", "-UserData:all", "-Keys:all", "-XMP:all", *paths[i:i + CHUNK]],
                       text=True).stdout
        for item in json.loads(out) if out.strip() else []:
            path = item.pop("SourceFile")
            found[path] = set(item)
    return found


@lru_cache(maxsize=1)
def writable_names() -> frozenset:
    out = proc.run([exiftool(), "-listw"], text=True).stdout
    return frozenset(t.lower() for line in out.splitlines()[1:] for t in line.split())


def tag_name(tag: str) -> str:
    return tag.split(":", 1)[-1]


@dataclass
class Match:
    current: Track
    saved: Track
    sets: dict
    blob_sets: dict
    deletes: list
    by_number: bool = False


def diff_tracks(current: Track, saved: Track, fields: set, prune: bool):
    sets, blob_sets, deletes, skipped = {}, {}, [], []
    writable = writable_names()

    def wanted(tag):
        name = tag_name(tag).lower()
        if fields and name not in fields:
            return False
        if name not in writable:
            skipped.append(tag)
            return False
        return True

    for tag, value in saved.tags.items():
        if wanted(tag) and current.tags.get(tag) != value:
            sets[tag] = value
    for tag, hashes in saved.blobs.items():
        if wanted(tag) and current.blobs.get(tag) != hashes:
            blob_sets[tag] = hashes
    if prune:
        for tag in list(current.tags) + list(current.blobs):
            if tag not in saved.tags and tag not in saved.blobs and wanted(tag):
                deletes.append(tag)
    return sets, blob_sets, deletes, skipped


def write_match(m: Match, blob_dir: Path) -> str | None:
    """Write one file with exiftool; returns an error text or None."""
    # Tags are written with their group (ItemList:Album): without a group exiftool writes XMP instead.
    cmd = [exiftool(), "-q", "-overwrite_original", "-P", "-charset", "filename=UTF8"]
    for tag, value in m.sets.items():
        for v in (value if isinstance(value, list) else [value]):
            cmd.append(f"-{tag}={v}")
    for tag, hashes in m.blob_sets.items():
        for h in hashes:
            cmd.append(f"-{tag}<={blob_dir / h}")
    for tag in m.deletes:
        cmd.append(f"-{tag}=")
    cmd.append(m.current.path)
    done = proc.run(cmd)
    leftover = Path(m.current.path + "_exiftool_tmp")
    if leftover.exists():
        leftover.unlink()
    message = done.stderr.decode("utf-8", "replace").strip()
    if done.returncode != 0 or "Warning" in message or "Error" in message:
        return message or f"exiftool exited with {done.returncode}"
    return None


def clean_file_names(tracks: list, overwrite: bool = False) -> None:
    """Rename files to 'NN Title.ext' ('D-NN Title.ext' for several discs), so no download id stays in a name."""
    for t in tracks:
        if t.number is None:
            continue
        disc, number = t.number
        total = re.search(r"of\s+(\d+)", pick(t.tags, "disc") or "")
        prefix = f"{disc}-{number:02d}" if total and int(total.group(1)) > 1 else f"{number:02d}"
        title = re.sub(r'[\\/:*?"<>|]+', "_", pick(t.tags, "title")).strip(" .")[:120] or "Track"
        old = Path(t.path)
        new = old.with_name(f"{prefix} {title}{old.suffix}")
        if new != old and (overwrite or not new.exists()):
            os.replace(old, new)
            t.path = str(new)
