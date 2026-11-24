"""Audio work with ffmpeg, ffprobe, flac and exiftool."""

import hashlib
import json
import os
import shutil
from pathlib import Path

from hist import proc, tags
from hist.errors import HistError
from hist.tags import Match, Track


class MediaError(HistError):
    pass


# The conversion: every stream is kept (the cover is copied as it is), the audio becomes ALAC, and the FLAC's tags
# are carried over. -fflags +bitexact keeps ffmpeg from writing its own Encoder tag.
ALAC_ARGS = ["-map", "0", "-c:a", "alac", "-c:v", "copy", "-map_metadata", "0"]


def alac_command(source: Path, out: Path) -> list:
    return ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(source), *ALAC_ARGS, "-fflags", "+bitexact", str(out)]


def duration(path: Path) -> float:
    out = proc.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], text=True
    ).stdout.strip()
    return float(out) if out else -1.0


def pcm_md5(path: Path) -> str:
    """Hash of the decoded audio (32-bit PCM), so a FLAC and its ALAC copy can be compared sample by sample."""
    return proc.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-map", "0:a:0", "-c:a", "pcm_s32le", "-f", "md5", "-"],
        text=True,
    ).stdout.strip()


def audio_md5(path: Path) -> str:
    return proc.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-map", "0:a", "-f", "md5", "-"], text=True
    ).stdout.strip()


def audio_packets(path: Path) -> str:
    """Hash of the encoded audio packets, unchanged by a container rebuild."""
    return proc.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-map", "0:a", "-c", "copy", "-f", "md5", "-"], text=True
    ).stdout.strip()


def decodes_cleanly(path: Path) -> bool:
    if path.suffix.lower() == ".flac" and shutil.which("flac"):
        return proc.run(["flac", "-t", "-s", path]).returncode == 0
    done = proc.run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-map", "0:a", "-f", "null", "-"])
    return done.returncode == 0 and not done.stderr.strip()


def readable(path: Path) -> bool:
    return proc.run(["ffprobe", "-v", "error", "-i", path]).returncode == 0


def has_store_protection(path: Path) -> bool:
    """Store purchases keep buyer and transaction data inside the audio track's sample description."""
    out = proc.run([tags.exiftool(), "-q", "-s3", "-a", "-u", "-SchemeType", path], text=True).stdout
    return bool(out.strip())


def store_protected(paths: list) -> set:
    """The paths, of those given, whose files still carry store purchase data (CHUNK files per exiftool run)."""
    found = set()
    for i in range(0, len(paths), tags.CHUNK):
        out = proc.run(
            [
                tags.exiftool(),
                "-q",
                "-j",
                "-a",
                "-u",
                "-charset",
                "filename=UTF8",
                "-SchemeType",
                *paths[i : i + tags.CHUNK],
            ],
            text=True,
        ).stdout
        found |= {item["SourceFile"] for item in (json.loads(out) if out.strip() else []) if item.get("SchemeType")}
    return found


def rebuild_container(path: Path) -> None:
    """Copy the streams into a fresh MP4 container without re-encoding; store purchase data is dropped."""
    tmp = path.with_name(f".{path.stem}.rebuild.m4a")
    before = audio_md5(path)
    done = proc.run(
        ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", path, "-map", "0", "-c", "copy", "-map_metadata", "0", tmp],
        text=True,
    )
    if done.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise MediaError("rebuilding the container failed: " + done.stderr.strip())
    if audio_md5(tmp) != before:
        tmp.unlink(missing_ok=True)
        raise MediaError("the audio differs after rebuilding the container; the original was kept")
    os.replace(tmp, path)


def strip_and_tag(saved: Track, path: Path, covers: Path) -> None:
    """Delete every tag of an M4A file (store purchase data included) and write the catalog's tags.

    The audio is not touched: no re-encoding and no conversion, only the metadata atoms change.
    """
    done = proc.run(
        [
            tags.exiftool(),
            "-q",
            "-overwrite_original",
            "-P",
            "-charset",
            "filename=UTF8",
            *(f"-{g}:all=" for g in tags.STRIP_GROUPS),
            path,
        ]
    )
    if done.returncode != 0:
        raise MediaError("stripping failed: " + done.stderr.decode("utf-8", "replace").strip())
    empty = Track(str(path), str(path.parent), {}, {})
    sets, blob_sets, deletes, _ = tags.diff_tracks(empty, saved, set(), False)
    error = tags.write_match(Match(empty, saved, sets, blob_sets, deletes), covers)
    if error:
        raise MediaError("writing the catalog's tags failed: " + error)
    left = proc.run(
        [tags.exiftool(), "-q", "-j", "-a", "-u", "-G1", "-b", *(f"-{g}:all" for g in tags.STRIP_GROUPS), path]
    ).stdout.decode("utf-8")
    found = {k for k in json.loads(left)[0] if k != "SourceFile"} if left.strip() else set()
    extra = found - set(saved.tags) - set(saved.blobs)
    if extra:
        raise MediaError("tags other than the catalog's remain: " + ", ".join(sorted(extra)))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def free_bytes(path: Path) -> int:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free
