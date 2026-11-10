"""The catalog: the exact tags and cover of every track, the single source of truth.

tracks.json holds {"format": 2, "tracks": [{"file": ..., "tags": {...}, "blobs": {...}}]}. "file" is the path the
track has inside the Music library (relative to the library folder); covers are stored in covers/<sha256>.
"""
import hashlib
import json
import os
from pathlib import Path

from hist import matching, proc, state, tags
from hist.config import Config
from hist.errors import HistError
from hist.tags import Track

FORMAT = 2
POLICY_DROP = ("ItemList:Comment", "ItemList:Encoder")
PROTECTED_ADD = set(POLICY_DROP)
PROTECTED_REMOVE = {"ItemList:DiskNumber", "ItemList:Title", "ItemList:Album", "ItemList:AlbumArtist",
                    "ItemList:Artist", "ItemList:TrackNumber"}


class CatalogError(HistError):
    pass


def read_records(config: Config) -> list[dict]:
    if not config.tracks_file.exists():
        return []
    data = json.loads(config.tracks_file.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise CatalogError(f"{config.tracks_file}: unsupported format {data.get('format')!r}")
    return data["tracks"]


def write_records(config: Config, records: list[dict]) -> None:
    state.keep_history(config.tracks_file, config.state / "history")
    state.write_json(config.tracks_file, {"format": FORMAT, "tracks": records})


def load(config: Config) -> list[Track]:
    root = str(config.library)
    return [Track(str(config.library / r["file"]), root, r["tags"], r["blobs"]) for r in read_records(config)]


def albums(config: Config) -> list[dict]:
    return matching.albums(load(config))


def short_tag(name: str) -> str:
    """'Genre' -> 'ItemList:Genre'; a name with a group is kept."""
    return name if ":" in name else f"ItemList:{name}"


def select_album(records: list[dict], text: str) -> str:
    """The one album name that contains text (case and punctuation ignored; an exact match wins)."""
    wanted = tags.norm(text)
    names = sorted({r["tags"]["ItemList:Album"] for r in records if wanted in tags.norm(r["tags"]["ItemList:Album"])})
    exact = [n for n in names if tags.norm(n) == wanted]
    names = exact or names
    if len(names) != 1:
        raise CatalogError(f"'{text}' must match exactly one album; it matches: {', '.join(names) or 'none'}")
    return names[0]


def record_number(record: dict) -> tuple:
    track = record["tags"].get("ItemList:TrackNumber", "").split()
    disc = record["tags"].get("ItemList:DiskNumber", "1").split()
    return (int(disc[0]) if disc else 1, int(track[0]) if track else 0)


def pick_records(records: list[dict], album: str, disc: int | None, track: int | None) -> list[dict]:
    picked = [r for r in records if r["tags"]["ItemList:Album"] == album]
    if track is not None:
        picked = [r for r in picked if record_number(r)[1] == track and (disc is None or record_number(r)[0] == disc)]
    elif disc is not None:
        picked = [r for r in picked if record_number(r)[0] == disc]
    if not picked:
        raise CatalogError("no such track")
    return sorted(picked, key=record_number)


def set_tag(config: Config, album_text: str, tag: str, value: str | None, disc=None, track=None) -> tuple:
    """Set (value given) or remove (value None) one tag; returns (album, changed, selected)."""
    tag = short_tag(tag)
    if value is not None and tag in PROTECTED_ADD:
        raise CatalogError(f"{tag} is never stored in the catalog")
    if value is None and tag in PROTECTED_REMOVE:
        raise CatalogError(f"{tag} is required on every track")
    records = read_records(config)
    album = select_album(records, album_text)
    picked = pick_records(records, album, disc, track)
    changed = 0
    for r in picked:
        if value is not None:
            if r["tags"].get(tag) != value:
                r["tags"][tag] = value
                changed += 1
        elif r["tags"].pop(tag, None) is not None:
            changed += 1
    if changed:
        write_records(config, records)
    return album, changed, len(picked)


def remove_album(config: Config, album_text: str, dry_run: bool = False) -> dict:
    """Remove an album from the catalog folder; the library and the Music app are not touched.

    Removed: the album's tracks, its dates.json entries (and its artist's, when no other album of that artist is
    left), its progress records, and covers that nothing else uses. Every changed file is kept in
    state/history first. Returns what was (or, with dry_run, would be) removed.
    """
    records = read_records(config)
    album = select_album(records, album_text)
    keep = [r for r in records if r["tags"]["ItemList:Album"] != album]
    gone = [r for r in records if r["tags"]["ItemList:Album"] == album]
    folders = {r["file"].rsplit("/", 1)[0] for r in gone}

    doc = json.loads(config.dates_file.read_text(encoding="utf-8")) if config.dates_file.exists() else {"entries": []}
    left = [e for e in doc["entries"] if not (e.get("kind") == "album" and e.get("path") in folders)]
    artists_in_use = {r["file"].split("/")[0] for r in keep} | {e["path"].split("/")[0] for e in left
                                                                if e.get("kind") == "album"}
    left = [e for e in left if not (e.get("kind") == "artist" and e.get("path") not in artists_in_use)]
    dates_removed = [e["path"] for e in doc["entries"] if e not in left]

    used = {h for r in keep for hashes in r["blobs"].values() for h in hashes}
    covers = sorted({h for r in gone for hashes in r["blobs"].values() for h in hashes} - used)
    covers = [h for h in covers if (config.covers / h).exists()]

    if not dry_run:
        history = config.state / "history"
        write_records(config, keep)
        if dates_removed:
            state.keep_history(config.dates_file, history)
            state.write_json(config.dates_file, {**doc, "entries": left})
        for digest in covers:
            state.keep_history(config.covers / digest, history)
            (config.covers / digest).unlink()
        state.added(config.state).remove(album)
        state.converted(config.state).remove(album)
    return {"album": album, "tracks": len(gone), "dates": dates_removed, "covers": covers}


# -------------------------------------------------------------- spec files

def read_spec(path: Path) -> dict:
    """Read a spec file; a relative 'cover' is taken relative to the spec file's folder."""
    spec = json.loads(path.read_text(encoding="utf-8"))
    for key in ("album", "album_artist", "release", "discs", "tracks"):
        if key not in spec:
            raise CatalogError(f"{path.name}: '{key}' is missing")
    if spec.get("cover"):
        spec["cover"] = str((path.parent / Path(spec["cover"]).expanduser()).resolve())
    return spec


def spec_records(config: Config, spec: dict, flac_dir: Path) -> tuple:
    """The catalog records of a spec, and the cover bytes (from 'cover' or the first FLAC's picture)."""
    flacs = sorted(flac_dir.expanduser().glob("*.flac"))
    if not flacs:
        raise CatalogError(f"no FLAC files in {flac_dir}")
    if len(flacs) != len(spec["tracks"]):
        raise CatalogError(f"{flac_dir} has {len(flacs)} FLAC files but the spec lists {len(spec['tracks'])} tracks")
    undecided = [t for t in spec["tracks"] if t.get("composer") is None]
    if undecided:
        raise CatalogError(f"{len(undecided)} tracks of the spec have no composer decision (null)")
    if spec.get("cover"):
        cover = Path(spec["cover"]).expanduser()
        cover = cover if cover.is_absolute() else config.home / cover
        if not cover.is_file():
            raise CatalogError(f"the spec's cover does not exist: {cover}")
        picture = cover.read_bytes()
        if picture[:3] != b"\xff\xd8\xff" and picture[:8] != b"\x89PNG\r\n\x1a\n":
            raise CatalogError("the spec's cover is not a JPEG or PNG image")
    else:
        picture = proc.run(["metaflac", "--export-picture-to=-", flacs[0]]).stdout
        if not picture:
            raise CatalogError("the first FLAC file has no embedded picture; give the spec a 'cover'")
        others = {hashlib.sha256(proc.run(["metaflac", "--export-picture-to=-", f]).stdout).hexdigest()
                  for f in flacs[1:]} - {hashlib.sha256(picture).hexdigest()}
        if others:
            raise CatalogError("the FLAC files do not all carry the same picture; give the spec a 'cover'")
    digest = hashlib.sha256(picture).hexdigest()

    per_disc = {}
    for t in spec["tracks"]:
        per_disc[t["disc"]] = per_disc.get(t["disc"], 0) + 1
    date = spec["release"].replace("-", ":") + " 00:00:00Z"
    folder = spec["album"].replace(":", "_")             # the Music app writes ':' as '_' in folder names
    records = []
    for t in sorted(spec["tracks"], key=lambda x: (x["disc"], x["track"])):
        record_tags = {
            "ItemList:Title": t["title"], "ItemList:Artist": t["artist"], "ItemList:AlbumArtist": spec["album_artist"],
            "ItemList:Composer": t["composer"], "ItemList:Album": spec["album"], "ItemList:Genre": t["genre"],
            "ItemList:Copyright": t.get("copyright", spec.get("copyright")),
            "ItemList:TrackNumber": f"{t['track']} of {per_disc[t['disc']]}",
            "ItemList:ContentCreateDate": date,
            "ItemList:DiskNumber": f"{t['disc']} of {spec['discs']}",
        }
        for key in ("ItemList:Composer", "ItemList:Copyright"):
            if not record_tags[key]:
                record_tags.pop(key)                     # a blank value is stored as no tag at all
        prefix = f"{t['disc']}-" if spec["discs"] > 1 else ""
        name = f"{prefix}{t['track']:02d} {t['title']}.m4a"
        records.append({"file": f"{spec['album_artist']}/{folder}/{name}", "tags": record_tags,
                        "blobs": {"ItemList:CoverArt": [digest]}})
    return records, picture


def add_spec(config: Config, spec: dict, flac_dir: Path, dry_run: bool = False) -> int:
    records, picture = spec_records(config, spec, flac_dir)
    if dry_run:
        return len(records)
    existing = [r for r in read_records(config) if r["tags"]["ItemList:Album"] != spec["album"]]
    config.covers.mkdir(parents=True, exist_ok=True)
    cover = config.covers / records[0]["blobs"]["ItemList:CoverArt"][0]
    if not cover.exists():
        cover.write_bytes(picture)
    write_records(config, existing + records)
    return len(records)


# ------------------------------------------------------------------ import

def import_library(config: Config, source: Path) -> tuple:
    """Snapshot the tags of an existing library folder into the catalog, applying the tag policy."""
    if read_records(config):
        raise CatalogError(f"the catalog in {config.home} already holds tracks")
    found = tags.find_tracks([source], "m4a")
    if not found:
        raise CatalogError(f"no M4A files under {source}")
    records, no_disc = [], 0
    for t in tags.read_tracks(found, config.covers):
        record_tags = {k: v for k, v in t.tags.items() if k.startswith("ItemList:") and k not in POLICY_DROP}
        blobs = {k: v for k, v in t.blobs.items() if k.startswith("ItemList:")}
        no_disc += "ItemList:DiskNumber" not in record_tags
        records.append({"file": os.path.relpath(t.path, source), "tags": record_tags, "blobs": blobs})
    write_records(config, records)
    return len(records), no_disc


# ------------------------------------------------------------------- check

def check(config: Config) -> list[str]:
    """Problems with the catalog's files (an empty list when everything is consistent)."""
    problems = []
    try:
        records = read_records(config)
    except (CatalogError, json.JSONDecodeError, KeyError) as error:
        return [f"tracks.json: {error}"]
    for r in records:
        where = r.get("file", "?")
        t = r.get("tags", {})
        for key in ("ItemList:Title", "ItemList:Album", "ItemList:AlbumArtist", "ItemList:Artist",
                    "ItemList:TrackNumber", "ItemList:DiskNumber", "ItemList:ContentCreateDate"):
            if key not in t:
                problems.append(f"{where}: {key} is missing")
        for key in POLICY_DROP:
            if key in t:
                problems.append(f"{where}: {key} must not be stored")
        for digest in (h for hashes in r.get("blobs", {}).values() for h in hashes):
            cover = config.covers / digest
            if not cover.exists():
                problems.append(f"{where}: cover {digest[:12]} is missing")
    for digest in {h for r in records for hashes in r.get("blobs", {}).values() for h in hashes}:
        cover = config.covers / digest
        if cover.exists() and hashlib.sha256(cover.read_bytes()).hexdigest() != digest:
            problems.append(f"covers/{digest[:12]}: the file's content does not match its name")
    seen = {}
    for r in records:
        key = (r["tags"].get("ItemList:Album"), record_number(r))
        if key in seen:
            problems.append(f"{r['file']}: same album, disc and track as {seen[key]}")
        seen[key] = r["file"]
    return problems
