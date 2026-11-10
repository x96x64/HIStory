"""Checking the environment and the configuration (reads only)."""
import shutil
import sys

from history_music import catalog, dates, media, proc, state
from history_music.config import Config


def run(config: Config) -> int:
    failed = 0

    def line(ok: bool, text: str, required: bool = True) -> None:
        nonlocal failed
        mark = "ok  " if ok else ("FAIL" if required else "warn")
        print(f"[{mark}] {text}")
        failed += (not ok and required)

    line(sys.version_info >= (3, 12), f"Python {sys.version.split()[0]} (3.12 or newer)")
    for tool, required, why in (("ffmpeg", True, ""), ("ffprobe", True, ""), ("flac", True, ""),
                                ("metaflac", True, ""), ("exiftool", True, ""),
                                ("osascript", False, "needed by status --music, verify --music, refresh, evacuate, store-entries"),
                                ("SetFile", False, "needed by dates apply; install the Xcode command line tools")):
        path = shutil.which(tool)
        line(bool(path), f"{tool}: {path or 'not found'}" + (f" ({why})" if why and not path else ""), required)
    if shutil.which("ffmpeg"):
        encoders = proc.run(["ffmpeg", "-hide_banner", "-encoders"], text=True).stdout
        line(" alac " in encoders, "ffmpeg has the ALAC encoder")

    print(f"home: {config.home}")
    line(config.config_file.exists(), f"config: {config.config_file}" + ("" if config.config_file.exists()
                                                                         else " (missing; run 'hist init')"))
    problems = catalog.check(config)
    records = catalog.read_records(config) if not problems or config.tracks_file.exists() else []
    names = {r["tags"].get("ItemList:Album") for r in records}
    waiting = len(catalog.pending_specs(config)) if config.specs.is_dir() and not problems else 0
    line(not problems and (bool(records) or bool(waiting)),
         f"catalog: {len(records)} tracks, {len(names)} albums"
         + (f", {waiting} albums waiting in specs/" if waiting else "")
         + (f", {len(problems)} problems (run 'hist catalog check')" if problems else "")
         + ("" if records or waiting or problems else " (empty: add albums with specs/ or 'hist catalog import')"),
         required=bool(problems))
    try:
        entries = dates.entries(config.dates_file)
        line(True, f"dates: {len(entries)} entries", required=False)
    except (dates.DatesError, ValueError, KeyError) as error:
        line(False, f"dates: {error}")

    line(bool(config.downloads), "downloads: " + (", ".join(str(p) for p in config.downloads) or
                                                  "not set (config.toml [paths] downloads)"))
    for path in config.downloads:
        line(path.is_dir(), f"  {path}" + ("" if path.is_dir() else " (does not exist yet)"), required=False)
    line(config.library.is_dir() or config.auto_add.is_dir(), f"library: {config.library}"
         + ("" if config.library.is_dir() else " (the Music app creates it when the first album is added)"),
         required=False)
    line(config.auto_add.is_dir(), f"auto_add: {config.auto_add}", required=False)
    if config.store_album:
        print(f"store album: {config.store_album} ({config.store_file})")
    probe = config.downloads[0] if config.downloads else config.home
    free = media.free_bytes(probe) / 2**30
    line(free > config.min_free_gb, f"free disk space: {free:.0f} GB (min_free_gb = {config.min_free_gb:g})",
         required=False)
    print(f"converted: {len(state.converted(config.state).names())} albums, "
          f"in the library: {len(state.added(config.state).names())} albums")
    pid = state.holder(config.state, "convert")
    if pid:
        print(f"running: hist watch or convert (pid {pid})")
    return 1 if failed else 0
