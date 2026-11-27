"""The catalog: the exact tags and cover of every track, the single source of truth.

tracks.json holds {"format": 2, "tracks": [{"file": ..., "tags": {...}, "blobs": {...}}]}. "file" is the path the
track has inside the Music library (relative to the library folder); covers are stored in covers/<sha256>.
"""

import datetime
import hashlib
import json
import os
import re
from pathlib import Path

from hist import dates, matching, proc, state, tags
from hist.config import Config
from hist.errors import HistError
from hist.tags import Track

FORMAT = 2
RELEASE = re.compile(r"\d{4}-\d\d-\d\d")
POLICY_DROP = ("ItemList:Comment", "ItemList:Encoder")
PROTECTED_ADD = set(POLICY_DROP)
PROTECTED_REMOVE = {
    "ItemList:DiskNumber",
    "ItemList:Title",
    "ItemList:Album",
    "ItemList:AlbumArtist",
    "ItemList:Artist",
    "ItemList:TrackNumber",
}


class CatalogError(HistError):
    code = "catalog"


def check_record(record: object, where: str) -> None:
    """Raise CatalogError unless record has the shape of a catalog record."""
    if not isinstance(record, dict):
        raise CatalogError(f"{where}: a track must be an object")
    if not isinstance(record.get("file"), str):
        raise CatalogError(f"{where}: 'file' must be a string")
    where = f"{where} ({record['file']})"
    tag_values = record.get("tags")
    if not isinstance(tag_values, dict) or not all(isinstance(v, str) for v in tag_values.values()):
        raise CatalogError(f"{where}: 'tags' must be an object of strings")
    blobs = record.get("blobs")
    if not isinstance(blobs, dict) or not all(
        isinstance(v, list) and all(isinstance(h, str) for h in v) for v in blobs.values()
    ):
        raise CatalogError(f"{where}: 'blobs' must be an object of lists of digests")


def parse_records(path: Path) -> list[dict]:
    """The records of a tracks.json file; raises CatalogError when it is not valid JSON or is malformed."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CatalogError(f"{path} is not valid JSON: {error}") from None
    if not isinstance(data, dict):
        raise CatalogError(f"{path}: the top level must be an object (see docs/catalog-format.md)")
    if data.get("format") != FORMAT:
        raise CatalogError(
            f"{path}: unsupported format {data.get('format')!r}; "
            f"hist reads format {FORMAT} (see docs/catalog-format.md)"
        )
    records = data.get("tracks")
    if not isinstance(records, list):
        raise CatalogError(f"{path}: 'tracks' must be a list")
    for number, record in enumerate(records, 1):
        check_record(record, f"{path.name}: track {number}")
    return records


def read_records(config: Config) -> list[dict]:
    """The records of tracks.json (none when the file does not exist); see parse_records."""
    return parse_records(config.tracks_file) if config.tracks_file.exists() else []


def write_records(config: Config, records: list[dict], backup: state.Backup) -> None:
    backup.keep(config.tracks_file)
    state.write_json(config.tracks_file, {"format": FORMAT, "tracks": records})


def load(config: Config) -> list[Track]:
    root = str(config.library)
    return [Track(str(config.library / r["file"]), root, r["tags"], r["blobs"]) for r in read_records(config)]


def albums(config: Config) -> list[dict]:
    return matching.albums(load(config))


KNOWN_TAGS = [
    "Title",
    "Artist",
    "AlbumArtist",
    "Album",
    "Composer",
    "Genre",
    "Copyright",
    "TrackNumber",
    "DiskNumber",
    "ContentCreateDate",
    "Comment",
    "Encoder",
    "CoverArt",
    "Lyrics",
    "Grouping",
    "Description",
    "Compilation",
    "Rating",
    "Year",
    "Conductor",
    "Publisher",
]
CANONICAL = {name.lower(): name for name in KNOWN_TAGS}


def short_tag(name: str) -> str:
    """'Genre' -> 'ItemList:Genre'; a name with a group is kept. Known names are matched ignoring case."""
    group, _, bare = name.rpartition(":")
    bare = CANONICAL.get(bare.lower(), bare)
    if not group:
        return f"ItemList:{bare}"
    return f"ItemList:{bare}" if group.lower() == "itemlist" else f"{group}:{bare}"


def album_of(record: dict) -> str:
    """The album name of a record ('' when it has none)."""
    return record["tags"].get("ItemList:Album", "")


def select_album(records: list[dict], text: str, exact: bool = False) -> str:
    """The one album name that contains text (case and punctuation ignored; an exact match wins).

    With exact, the album's name must equal text character for character.
    """
    if exact:
        names = sorted({album_of(r) for r in records if album_of(r) == text})
        if not names:
            raise CatalogError(f"no album is named '{text}'; run 'hist catalog list' to see the names")
        return names[0]
    wanted = tags.norm(text)
    names = sorted({album_of(r) for r in records if wanted in tags.norm(album_of(r))})
    exact = [n for n in names if tags.norm(n) == wanted]
    names = exact or names
    if len(names) != 1:
        if names:
            raise CatalogError(
                f"'{text}' must match exactly one album; it matches: {', '.join(names)}. "
                "Give more of the name, or pass --exact with the full name"
            )
        raise CatalogError(f"'{text}' matches no album; run 'hist catalog list' to see the names")
    return names[0]


def record_number(record: dict) -> tuple:
    """(disc, track) of a record; raises CatalogError when a number is not a number."""
    track = record["tags"].get("ItemList:TrackNumber", "").split()
    disc = record["tags"].get("ItemList:DiskNumber", "1").split()
    try:
        return (int(disc[0]) if disc else 1, int(track[0]) if track else 0)
    except ValueError:
        raise CatalogError(
            f"{record['file']}: TrackNumber '{' '.join(track)}' or DiskNumber '{' '.join(disc)}' is not a number"
        ) from None


def pick_records(records: list[dict], album: str, disc: int | None, track: int | None) -> list[dict]:
    picked = [r for r in records if album_of(r) == album]
    if track is not None:
        picked = [r for r in picked if record_number(r)[1] == track and (disc is None or record_number(r)[0] == disc)]
    elif disc is not None:
        picked = [r for r in picked if record_number(r)[0] == disc]
    if not picked:
        raise CatalogError(f"no such track in {album}; run 'hist catalog show \"{album}\" --exact' to see its tracks")
    return sorted(picked, key=record_number)


def set_tag(
    config: Config, album_text: str, tag: str, value: str | None, disc=None, track=None, exact: bool = False
) -> tuple:
    """Set (value given) or remove (value None) one tag; returns (album, changed, selected).

    The change is checked exactly like an operation of 'catalog edit' (see edit.check_operation).
    """
    from hist import edit

    records = read_records(config)
    album = select_album(records, album_text, exact)
    picked = pick_records(records, album, disc, track)
    op = {"op": "unset" if value is None else "set", "album": album, "tag": tag, "exact": True}
    if value is not None:
        op["value"] = value
    for key, number in (("disc", disc), ("track", track)):
        if number is not None:
            op[key] = number
    _, new, found = edit.compute(config, [op])
    if found:
        command = "catalog-set" if value is not None else "catalog-unset"
        write_records(config, new, state.Backup(config.state, command))
    return album, len(found), len(picked)


def remove_album(config: Config, album_text: str, dry_run: bool = False, exact: bool = False) -> dict:
    """Remove an album from the catalog folder; the library and the Music app are not touched.

    Removed: the album's tracks, its dates.json entries (and its artist's, when no other album of that artist is
    left), its progress records, and covers that nothing else uses. Every changed file is kept in
    one folder of state/backups first. Returns what was (or, with dry_run, would be) removed.
    """
    records = read_records(config)
    album = select_album(records, album_text, exact)
    keep = [r for r in records if album_of(r) != album]
    gone = [r for r in records if album_of(r) == album]
    folders = {r["file"].rsplit("/", 1)[0] for r in gone}

    try:
        doc = state.read_json(config.dates_file, {"entries": []})
        if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
            raise ValueError("'entries' must be a list")
    except ValueError as error:
        raise CatalogError(f"{config.dates_file} is malformed: {error}") from None
    left = [e for e in doc["entries"] if not (e.get("kind") == "album" and e.get("path") in folders)]
    artists_in_use = {r["file"].split("/")[0] for r in keep} | {
        e["path"].split("/")[0] for e in left if e.get("kind") == "album"
    }
    left = [e for e in left if not (e.get("kind") == "artist" and e.get("path") not in artists_in_use)]
    dates_removed = [e["path"] for e in doc["entries"] if e not in left]

    used = {h for r in keep for hashes in r["blobs"].values() for h in hashes}
    covers = sorted({h for r in gone for hashes in r["blobs"].values() for h in hashes} - used)
    covers = [h for h in covers if (config.covers / h).exists()]

    if not dry_run:
        backup = state.Backup(config.state, "catalog-remove")
        write_records(config, keep, backup)
        if dates_removed:
            backup.keep(config.dates_file)
            state.write_json(config.dates_file, {**doc, "entries": left})
        for digest in covers:
            backup.keep(config.covers / digest, f"covers/{digest}")
            (config.covers / digest).unlink()
        state.added(config.state).remove(album)
        state.converted(config.state).remove(album)
    return {"album": album, "tracks": len(gone), "dates": dates_removed, "covers": covers}


BACKUP_FILES = ("tracks.json", "dates.json", "tracks.json.absent", "dates.json.absent")
BACKUP_NAME = re.compile(r"^(\d{8}-\d{6})-(catalog|dates)")


def latest_backup(config: Config) -> Path | None:
    """The newest folder of state/backups that holds a tracks.json or a dates.json (or a marker that one was absent)."""
    folders = [
        d
        for d in (config.state / "backups").glob("*")
        if d.is_dir() and BACKUP_NAME.match(d.name) and any((d / n).is_file() for n in BACKUP_FILES)
    ]
    return max(folders, key=lambda d: (d.name[:15], d.stat().st_mtime_ns), default=None)


def undo(config: Config, dry_run: bool = False) -> dict:
    """Restore the files of the newest backup of the catalog or of dates.json (the caller holds the lock).

    The current tracks.json and dates.json that are replaced are kept first in a new backup folder, so that a
    second undo restores them again. A file that did not exist when the backup was made (marked 'name.absent') is
    removed. Covers of the backup that are missing from covers/ are put back. Returns
    {"from", "restored", "removed", "covers", "backup"}.
    """
    source = latest_backup(config)
    if source is None:
        raise CatalogError("there is no backup of the catalog in state/backups to restore")
    names = [n for n in ("tracks.json", "dates.json") if (source / n).is_file()]
    removed = [n for n in ("tracks.json", "dates.json") if (source / f"{n}.absent").is_file() and n not in names]
    if "tracks.json" in names:
        parse_records(source / "tracks.json")
    if "dates.json" in names:
        try:
            dates.entries(source / "dates.json")
        except dates.DatesError as error:
            raise CatalogError(f"{source / 'dates.json'} cannot be restored: {error}") from None
    cover_dir = source / "covers"
    covers = (
        sorted(c.name for c in cover_dir.iterdir() if not (config.covers / c.name).exists())
        if cover_dir.is_dir()
        else []
    )
    report = {
        "from": source.name,
        "restored": names,
        "removed": removed,
        "covers": covers,
        "backup": None,
        "dry_run": dry_run,
    }
    if dry_run:
        return report
    backup = state.Backup(config.state, "catalog-undo")
    for name in names + removed:
        backup.keep(config.home / name)
    for digest in covers:
        state.write_bytes(config.covers / digest, (cover_dir / digest).read_bytes())
    for name in names:
        state.write_bytes(config.home / name, (source / name).read_bytes())
    for name in removed:
        (config.home / name).unlink(missing_ok=True)
    report["backup"] = str(backup.path) if backup.path else None
    return report


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
    folder = flac_dir.expanduser()
    flacs = (
        sorted(p for p in folder.iterdir() if p.suffix.lower() == ".flac" and not p.name.startswith("."))
        if folder.is_dir()
        else []
    )
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
        others = {
            hashlib.sha256(proc.run(["metaflac", "--export-picture-to=-", f]).stdout).hexdigest() for f in flacs[1:]
        } - {hashlib.sha256(picture).hexdigest()}
        if others:
            raise CatalogError("the FLAC files do not all carry the same picture; give the spec a 'cover'")
    digest = hashlib.sha256(picture).hexdigest()
    return build_records(spec, digest), picture


def build_records(spec: dict, digest: str) -> list[dict]:
    """The catalog records a spec describes, with the cover whose SHA-256 is digest."""
    per_disc = {}
    for t in spec["tracks"]:
        per_disc[t["disc"]] = per_disc.get(t["disc"], 0) + 1
    date = spec["release"].replace("-", ":") + " 00:00:00Z"
    folder = spec["album"].replace(":", "_")  # the Music app writes ':' as '_' in folder names
    records = []
    for t in sorted(spec["tracks"], key=lambda x: (x["disc"], x["track"])):
        record_tags = {
            "ItemList:Title": t["title"],
            "ItemList:Artist": t["artist"],
            "ItemList:AlbumArtist": spec["album_artist"],
            "ItemList:Composer": t["composer"],
            "ItemList:Album": spec["album"],
            "ItemList:Genre": t["genre"],
            "ItemList:Copyright": t.get("copyright", spec.get("copyright")),
            "ItemList:TrackNumber": f"{t['track']} of {per_disc[t['disc']]}",
            "ItemList:ContentCreateDate": date,
            "ItemList:DiskNumber": f"{t['disc']} of {spec['discs']}",
        }
        for key in ("ItemList:Composer", "ItemList:Copyright"):
            if not record_tags[key]:
                record_tags.pop(key)  # a blank value is stored as no tag at all
        prefix = f"{t['disc']}-" if spec["discs"] > 1 else ""
        name = f"{prefix}{t['track']:02d} {t['title']}.m4a"
        records.append(
            {
                "file": f"{spec['album_artist']}/{folder}/{name}",
                "tags": record_tags,
                "blobs": {"ItemList:CoverArt": [digest]},
            }
        )
    return records


def check_spec(spec: dict) -> None:
    """Raise CatalogError, listing every problem, unless the spec describes a consistent album."""
    problems = []
    for key in ("album", "album_artist"):
        if not isinstance(spec.get(key), str) or not spec[key]:
            problems.append(f"'{key}' must be a non-empty string")
    release = spec.get("release")
    try:
        if not isinstance(release, str) or not RELEASE.fullmatch(release):
            raise ValueError
        datetime.date.fromisoformat(release)
    except ValueError:
        problems.append(f"'release' must be a date like 2001-02-03, not {release!r}")
    discs = spec.get("discs")
    if not isinstance(discs, int) or isinstance(discs, bool) or discs < 1:
        problems.append("'discs' must be an integer of at least 1")
        discs = None
    if not isinstance(spec.get("tracks"), list) or not spec["tracks"]:
        problems.append("'tracks' must be a non-empty list")
    else:
        seen = set()
        for number, t in enumerate(spec["tracks"], 1):
            if not isinstance(t, dict):
                problems.append(f"track {number}: must be an object")
                continue
            missing = [k for k in ("disc", "track", "title", "artist", "genre") if k not in t]
            if missing:
                problems.append(f"track {number}: {', '.join(missing)} missing")
                continue
            disc, track = t["disc"], t["track"]
            if any(not isinstance(n, int) or isinstance(n, bool) or n < 1 for n in (disc, track)):
                problems.append(f"track {number}: 'disc' and 'track' must be integers of at least 1")
                continue
            if discs is not None and disc > discs:
                problems.append(f"track {number}: disc {disc} is more than the {discs} discs of the album")
            if (disc, track) in seen:
                problems.append(f"track {number}: disc {disc}, track {track} is listed twice")
            seen.add((disc, track))
    if problems:
        raise CatalogError("the spec is invalid:\n" + "\n".join(problems))


def add_spec(config: Config, spec: dict, flac_dir: Path, dry_run: bool = False) -> int:
    check_spec(spec)
    for r in read_records(config):
        if album_of(r) == spec["album"] and r["tags"].get("ItemList:AlbumArtist") != spec["album_artist"]:
            raise CatalogError(
                f"the catalog already has an album named '{spec['album']}' by "
                f"'{r['tags'].get('ItemList:AlbumArtist', '')}'; 'catalog add' would replace it with the album of "
                f"'{spec['album_artist']}'. Run 'hist catalog remove' first if that is what you want"
            )
    records, picture = spec_records(config, spec, flac_dir)
    if dry_run:
        return len(records)
    existing = [r for r in read_records(config) if album_of(r) != spec["album"]]
    config.covers.mkdir(parents=True, exist_ok=True)
    cover = config.covers / records[0]["blobs"]["ItemList:CoverArt"][0]
    if not cover.exists():
        state.write_bytes(cover, picture)
    write_records(config, existing + records, state.Backup(config.state, "catalog-add"))
    return len(records)


# ------------------------------------------------------------- cover, export


def image_kind(picture: bytes) -> str | None:
    """'jpg' or 'png' for the bytes of such an image, else None."""
    if picture[:3] == b"\xff\xd8\xff":
        return "jpg"
    return "png" if picture[:8] == b"\x89PNG\r\n\x1a\n" else None


def set_cover(config: Config, album_text: str, image: Path, exact: bool = False) -> dict:
    """Store image in covers/ (named by its SHA-256) and make it the cover of every track of the album.

    The previous tracks.json is kept in state/backups. Returns {"album", "cover", "tracks", "changed"}.
    """
    image = image.expanduser()
    if not image.is_file():
        raise CatalogError(f"{image} is not a file")
    picture = image.read_bytes()
    if image_kind(picture) is None:
        raise CatalogError(f"{image} is not a JPEG or PNG image")
    digest = hashlib.sha256(picture).hexdigest()
    records = read_records(config)
    album = select_album(records, album_text, exact)
    picked = [r for r in records if album_of(r) == album]
    changed = [r for r in picked if r["blobs"].get("ItemList:CoverArt") != [digest]]
    if changed:
        stored = config.covers / digest
        if not stored.exists():
            config.covers.mkdir(parents=True, exist_ok=True)
            state.write_bytes(stored, picture)
        for r in changed:
            r["blobs"]["ItemList:CoverArt"] = [digest]
        write_records(config, records, state.Backup(config.state, "catalog-cover"))
    return {"album": album, "cover": digest, "tracks": len(picked), "changed": len(changed)}


def export_spec(config: Config, album_text: str, exact: bool = False, cover_to: Path | None = None) -> tuple:
    """A spec (see read_spec) that 'catalog add' turns back into this album's records.

    Returns (spec, warnings). A spec cannot hold every tag: tags it cannot express, and a file name that the
    spec would name differently, are listed in warnings. The spec's 'cover' is the album's cover: the file
    cover_to when given (copied there), otherwise the path of the image in covers/.
    """
    records = read_records(config)
    album = select_album(records, album_text, exact)
    picked = sorted((r for r in records if album_of(r) == album), key=record_number)
    first_tags = picked[0]["tags"]
    warnings = []

    def of(r: dict, key: str) -> str:
        return r["tags"].get(f"ItemList:{key}", "")

    copyrights = [of(r, "Copyright") for r in picked]
    common = max(sorted(set(copyrights)), key=copyrights.count)
    tracks = []
    for r in picked:
        disc, number = record_number(r)
        track = {
            "disc": disc,
            "track": number,
            "title": of(r, "Title"),
            "artist": of(r, "Artist"),
            "composer": of(r, "Composer"),
            "genre": of(r, "Genre"),
        }
        if of(r, "Copyright") != common:
            track["copyright"] = of(r, "Copyright")
        tracks.append(track)
    discs = first_tags.get("ItemList:DiskNumber", "1 of 1").split()
    spec = {
        "album": album,
        "album_artist": of(picked[0], "AlbumArtist"),
        "release": of(picked[0], "ContentCreateDate")[:10].replace(":", "-"),
        "discs": int(discs[-1]) if len(discs) == 3 else 1,
    }
    if common:
        spec["copyright"] = common
    covers = {tuple(r["blobs"].get("ItemList:CoverArt", ())) for r in picked}
    if len(covers) > 1:
        warnings.append("the tracks have different covers; the spec names the first track's cover")
    digests = picked[0]["blobs"].get("ItemList:CoverArt")
    if digests:
        source = config.covers / digests[0]
        if not source.is_file():
            warnings.append(f"cover {digests[0][:12]} is missing from covers/; the spec has no cover")
        elif cover_to is None:
            spec["cover"] = str(source)
        else:
            picture = source.read_bytes()
            target = cover_to.with_name(f"{cover_to.stem}-cover.{image_kind(picture) or 'jpg'}")
            state.write_bytes(target, picture)
            spec["cover"] = target.name
    spec["tracks"] = tracks

    again = {r["file"]: r["tags"] for r in build_records(spec, digests[0] if digests else "")}
    lost = set()
    for r in picked:
        if r["file"] not in again:
            warnings.append(f"{r['file']}: the spec would name this file differently")
            continue
        for tag in set(r["tags"]) | set(again[r["file"]]):
            if r["tags"].get(tag) != again[r["file"]].get(tag):
                lost.add(tag)
    if lost:
        warnings.append("tags that a spec cannot express or would write differently: " + ", ".join(sorted(lost)))
    return spec, warnings


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
    write_records(config, records, state.Backup(config.state, "catalog-import"))
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
        for key in (
            "ItemList:Title",
            "ItemList:Album",
            "ItemList:AlbumArtist",
            "ItemList:Artist",
            "ItemList:TrackNumber",
            "ItemList:DiskNumber",
            "ItemList:ContentCreateDate",
        ):
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
        try:
            key = (album_of(r), record_number(r))
        except CatalogError as error:
            problems.append(str(error))
            continue
        if key in seen:
            problems.append(f"{r['file']}: same album, disc and track as {seen[key]}")
        seen[key] = r["file"]
    return problems
