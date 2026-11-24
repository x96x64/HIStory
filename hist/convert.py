"""Converting complete downloads: tags into the FLAC files, ALAC conversion, checks, then the FLAC is deleted.

Nothing here writes to the Music app or the Music library folder. The library is only read, to copy out a store
file named in config.toml [store].
"""

import hashlib
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from hist import catalog, matching, media, proc, state, tags
from hist.config import Config
from hist.errors import HistError
from hist.log import log
from hist.tags import Track


class ConvertError(HistError):
    pass


@dataclass
class Options:
    only: str = ""
    keep_flac: bool = False
    dry_run: bool = False


# ------------------------------------------------------------------ one file


def of_pair(text: str):
    m = re.match(r"\s*(\d+)\s+of\s+(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def iso_date(text: str) -> str:
    m = re.match(r"(\d{4}):(\d\d):(\d\d) (\d\d):(\d\d):(\d\d)Z", text or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T{m.group(4)}:{m.group(5)}:{m.group(6)}Z" if m else text


def vorbis_tags(t: dict) -> dict:
    """The Vorbis comments that, after ffmpeg's conversion, give exactly the catalog's M4A tags."""
    # ffmpeg turns TRACKNUMBER=1/12 into 'N of M' and DATE=...T00:00:00Z into the M4A release date.
    n, total = of_pair(t.get("ItemList:TrackNumber"))
    d, discs = of_pair(t.get("ItemList:DiskNumber"))
    out = {
        "TITLE": t["ItemList:Title"],
        "ARTIST": t["ItemList:Artist"],
        "ALBUMARTIST": t["ItemList:AlbumArtist"],
        "ALBUM": t["ItemList:Album"],
        "GENRE": t["ItemList:Genre"],
        "DATE": iso_date(t["ItemList:ContentCreateDate"]),
        "TRACKNUMBER": f"{n}/{total}",
        "DISCNUMBER": f"{d}/{discs}",
    }
    for key, tag in (("COMPOSER", "ItemList:Composer"), ("COPYRIGHT", "ItemList:Copyright")):
        if t.get(tag):
            out[key] = t[tag]
    return out


def tag_flac(flac: Path, saved: Track, covers: Path) -> None:
    expected = vorbis_tags(saved.tags)
    cover = covers / saved.blobs["ItemList:CoverArt"][0]
    # metaflac cannot remove pictures and all tags in one call
    first = proc.run(["metaflac", "--preserve-modtime", "--remove", "--block-type=PICTURE", flac], text=True)
    if first.returncode:
        raise ConvertError("metaflac could not remove the old pictures: " + first.stderr.strip()[:200])
    cmd = ["metaflac", "--preserve-modtime", "--no-utf8-convert", "--remove-all-tags"]
    cmd += [f"--set-tag={k}={v}" for k, v in expected.items()]
    cmd += [f"--import-picture-from=3||||{cover}", flac]
    second = proc.run(cmd, text=True)
    if second.returncode:
        raise ConvertError("metaflac could not write the tags: " + second.stderr.strip())
    shown = proc.run(["metaflac", "--export-tags-to=-", flac], text=True).stdout
    found = dict(line.split("=", 1) for line in shown.splitlines() if "=" in line)
    if found != expected:
        raise ConvertError(
            f"the FLAC tags differ from what was written: {sorted(set(found.items()) ^ set(expected.items()))[:4]}"
        )
    with tempfile.TemporaryDirectory() as tmp:
        picture = Path(tmp) / "cover"
        proc.run(["metaflac", f"--export-picture-to={picture}", flac])
        if (
            not picture.exists()
            or hashlib.sha256(picture.read_bytes()).hexdigest() != saved.blobs["ItemList:CoverArt"][0]
        ):
            raise ConvertError("the cover inside the FLAC is not the catalog's image")


def to_alac(flac: Path, out: Path) -> None:
    out.unlink(missing_ok=True)
    done = proc.run(media.alac_command(flac, out), text=True)
    if done.returncode or not out.exists():
        out.unlink(missing_ok=True)
        raise ConvertError("ffmpeg failed: " + done.stderr.strip()[-200:])


def check_m4a(flac: Path, m4a: Path, saved: Track) -> None:
    want = media.pcm_md5(flac)
    if not want or media.pcm_md5(m4a) != want:
        raise ConvertError("the M4A does not decode to the same samples as the FLAC")
    before, after = media.duration(flac), media.duration(m4a)
    if before < 0 or abs(before - after) > 0.5:
        raise ConvertError(f"durations differ ({before:.2f}s against {after:.2f}s)")
    got = tags.read_tracks([(str(m4a.parent), str(m4a))])
    if not got:
        raise ConvertError("the M4A tags could not be read")
    if got[0].tags != saved.tags or got[0].blobs != saved.blobs:
        diff = {
            k: (got[0].tags.get(k), saved.tags.get(k))
            for k in set(got[0].tags) | set(saved.tags)
            if got[0].tags.get(k) != saved.tags.get(k)
        }
        raise ConvertError(f"the M4A tags differ from the catalog: {diff or 'the cover differs'}")
    stray = tags.metadata_atoms(str(m4a)) - set(saved.tags) - set(saved.blobs)
    if stray:
        raise ConvertError("tags that are not in the catalog: " + ", ".join(sorted(stray)))


def process_file(flac: Path, saved: Track, covers: Path, keep_flac: bool) -> Path:
    tag_flac(flac, saved, covers)
    out = flac.with_suffix(".m4a")
    to_alac(flac, out)
    check_m4a(flac, out, saved)
    track = tags.read_tracks([(str(out.parent), str(out))])[0]
    tags.clean_file_names([track], overwrite=True)  # replaces a stale file of an interrupted run
    final = Path(track.path)
    check_m4a(flac, final, saved)  # once more under its final name
    if not keep_flac:
        flac.unlink()  # only now: every check passed
    return final


# ------------------------------------------------------------------- albums


def selected(album: dict, only: str) -> bool:
    return not only or tags.norm(only) in tags.norm(album["name"])


def album_state(config: Config, album: dict, folders: list, all_albums: list):
    """(folder, problem): the download folder of the album and why it cannot be processed now (None if it can)."""
    alias = config.aliases.get(album["name"])
    if alias:
        album = {**album, "key": (tags.norm(alias), album["key"][1])}
    folder, why = matching.pick_folder(album, folders, 0.9)
    if folder is not None:
        # a folder that fits another album better belongs to that one (a short name inside a longer one)
        mine = tags.similarity(folder.album, album["key"][0], "substring")
        for other in all_albums:
            if (
                other["name"] != album["name"]
                and other["key"] != album["key"]
                and tags.similarity(folder.album, other["key"][0], "substring") > mine + 0.005
                and tags.similarity(folder.artist, other["key"][1], "substring") >= 0.9
            ):
                return None, f"{folder.path} belongs to the better-matching album {other['name']}"
    if folder is None:
        return None, why
    problems = matching.check_ready(folder, "flac" if folder.has_flac else "m4a", deep=False)
    return folder, "; ".join(problems) if problems else None


def pair_album(config: Config, album: dict, folder) -> list:
    """(FLAC path, catalog track) for every file of the folder."""
    flacs = sorted(p for p in folder.files if p.suffix.lower() == ".flac")
    current = tags.read_tracks([(str(folder.path), str(p)) for p in flacs])
    if config.aliases.get(album["name"]):
        for t in current:  # the download folder is named differently; compare as the catalog's album
            t.album = tags.norm(album["name"])
    renumber = config.renumber.get(album["name"])
    if renumber:  # one disc of a larger set, numbered on from the earlier discs
        for t in current:
            if t.number is not None:
                t.number = (renumber["disc"], t.number[1] - renumber["offset"])
    pairs, unmatched, _ = matching.pair_tracks(album["tracks"], current, "substring", 0.9, 0.85, True)
    if unmatched or len(pairs) != len(current):
        raise ConvertError("not every FLAC could be matched to a catalog track; nothing was written")
    return sorted(((Path(current[ci].path), album["tracks"][si]) for ci, si in pairs), key=lambda p: p[1].number)


def remove_stale_outputs(config: Config, all_albums: list, done: set, only: str) -> int:
    """An interrupted run can leave M4A files next to the FLAC files they came from: a half-written output (same
    name stem as its FLAC), or a finished one when the run stopped before the FLAC was deleted. While the FLAC exists
    it is the master, so such files are removed and made again. Folders of finished albums are never touched."""
    removed = 0
    for root in config.sources:
        if not root.is_dir():
            continue
        for directory in sorted({p.parent for p in root.rglob("*.flac")}):
            flacs = sorted(directory.glob("*.flac"))
            m4as = sorted(directory.glob("*.m4a"))
            if not m4as:
                continue
            probe = tags.read_tracks([(str(directory), str(flacs[0]))])
            if not probe:
                continue
            first = probe[0]
            album = next(
                (
                    a
                    for a in all_albums
                    if tags.similarity(tags.norm(tags.pick(first.tags, "album")), a["key"][0], "substring") >= 0.9
                    and tags.similarity(tags.norm(tags.pick(first.tags, "artist")), a["key"][1], "substring") >= 0.9
                ),
                None,
            )
            if album is None or album["name"] in done or not selected(album, only):
                continue
            stems = {p.stem for p in flacs}
            keys = {(t.title, t.number) for t in tags.read_tracks([(str(directory), str(p)) for p in flacs])}
            for t in tags.read_tracks([(str(directory), str(p)) for p in m4as]):
                path = Path(t.path)
                if path.stem in stems or not media.readable(path) or (t.title and (t.title, t.number) in keys):
                    path.unlink(missing_ok=True)
                    removed += 1
    return removed


def stage_store_file(config: Config, done: set) -> bool:
    """Copy the store file out of the Music library into the staging folder (the library is only read)."""
    src, dst = config.store_library_copy, config.store_staged
    if src is None or dst.exists() or not src.exists() or config.store_album in done:
        return False
    if time.time() - src.stat().st_mtime < 40:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if media.sha256(dst) != media.sha256(src):
        dst.unlink()
        return False
    return True


def run_store_album(config: Config, album: dict, folder) -> int:
    """Stand-alone store M4A files: rebuild the container (drops purchases), strip every tag, write the catalog's."""
    m4as = sorted(p for p in folder.files if p.suffix.lower() == ".m4a")
    for path in m4as:
        if media.has_store_protection(path):
            media.rebuild_container(path)
    before = tags.read_tracks([(str(p.parent), str(p)) for p in m4as])
    pairs, unmatched, _ = matching.pair_tracks(album["tracks"], before, "substring", 0.9, 0.85, True)
    if unmatched or len(pairs) != len(before):
        raise ConvertError("not every store file could be matched to a catalog track; nothing was changed")
    for ci, si in pairs:
        media.strip_and_tag(album["tracks"][si], Path(before[ci].path), config.covers)
    after = tags.read_tracks([(str(p.parent), str(p)) for p in m4as])
    tags.clean_file_names(after)
    for t in after:
        ref = [s for s in album["tracks"] if s.number == t.number]
        if not ref or t.tags != ref[0].tags or t.blobs != ref[0].blobs or media.has_store_protection(Path(t.path)):
            raise ConvertError("the processed store file does not match the catalog")
    return len(after)


@dataclass
class Pass:
    converted: int = 0
    low_disk: tuple = ()


def run_once(config: Config, options: Options, stopping=lambda: False) -> Pass:
    """Convert every complete album once, oldest release first. Raises ConvertError on the first problem."""
    progress = state.converted(config.state)
    done = progress.names() | state.added(config.state).names()  # an album in the library is finished
    if not options.dry_run and stage_store_file(config, done):
        log.info(f"Copied the store file of {config.store_album} out of the library for processing.")
    all_albums = catalog.albums(config)
    if not options.dry_run and remove_stale_outputs(config, all_albums, done, options.only):
        log.info("Removed M4A files left by an interrupted run; their FLAC files are converted again.")
    folders = matching.scan(config.sources)
    result = Pass()
    low = []
    for album in all_albums:
        if stopping():
            break
        if album["name"] in done or not selected(album, options.only):
            continue
        folder, why = album_state(config, album, folders, all_albums)
        if folder is None or why:
            continue
        if not folder.has_flac:
            if album["name"] == config.store_album and any(
                media.has_store_protection(p) for p in folder.files if p.suffix.lower() == ".m4a"
            ):
                if options.dry_run:
                    log.info(f"{album['name']}: the store file would be cleaned and retagged")
                    continue
                log.info(f"Processing the store file of {album['name']}")
                n = run_store_album(config, album, folder)
                progress.add(album["name"], tracks=n)
                log.info(f"Done: {album['name']} ({n} track, store data removed, tags rewritten)")
                result.converted += 1
            continue
        if options.dry_run:
            show_pairing(config, album, folder)
            continue
        # a final, deep check right before anything is written: sizes stable and every FLAC decodes
        if matching.check_ready(folder, "flac", deep=True):
            continue
        size = sum(p.stat().st_size for p in folder.files if p.suffix.lower() == ".flac")
        need = int(size * (1.2 if options.keep_flac else 0.6)) + int(config.min_free_gb * 2**30)
        free = media.free_bytes(folder.path)
        if free < need:
            low.append(f"{album['name']} needs about {need / 2**30:.1f} GB free, {free / 2**30:.1f} GB is free")
            continue
        log.info(f"Converting {album['name']} ({folder.count} tracks)")
        try:
            for flac, saved in pair_album(config, album, folder):
                process_file(flac, saved, config.covers, options.keep_flac)
        except (ConvertError, media.MediaError) as error:
            raise ConvertError(f"{album['name']}: {error} (the FLAC files that were not converted are kept)") from None
        progress.add(album["name"], tracks=folder.count)
        log.info(
            f"Done: {album['name']} ({folder.count} tracks"
            + (", FLAC files kept)" if options.keep_flac else ", FLAC files removed after every check)")
        )
        result.converted += 1
    result.low_disk = tuple(low)
    return result


def show_pairing(config: Config, album: dict, folder) -> None:
    pairs = pair_album(config, album, folder)
    log.info(f"{album['name']}: {len(pairs)} tracks in {folder.path}")
    for flac, saved in pairs:
        disc, number = saved.number
        log.info(
            f"  {disc}-{number:02d} {media.duration(flac):8.2f}s  {flac.name}  ->  {tags.pick(saved.tags, 'title')}"
        )


def pending(config: Config, only: str = "") -> list:
    """Albums that are neither converted nor present as converted files, oldest release first.

    The store album is never waited for: it counts only while a store file that still carries purchase data sits
    in the library or the staging folder.
    """
    done = state.converted(config.state).names() | state.added(config.state).names()
    all_albums = catalog.albums(config)
    folders = matching.scan(config.sources)
    out = []
    for album in all_albums:
        if album["name"] in done or not selected(album, only):
            continue
        if album["name"] == config.store_album:
            files = [p for p in (config.store_staged, config.store_library_copy) if p.exists()]
            if any(media.has_store_protection(p) for p in files):
                out.append(album["name"])
            continue
        folder, _ = album_state(config, album, folders, all_albums)
        if folder is None or folder.has_flac:
            out.append(album["name"])
    return out
