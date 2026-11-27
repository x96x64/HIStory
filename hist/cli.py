"""The 'hist' command line."""

import argparse
import json
import logging
import os
import shutil
import signal
import sys
import traceback
from pathlib import Path

from hist import agent, catalog, dates, proc, runtime, state
from hist import config as config_mod
from hist.errors import HistError
from hist.log import emit_json, emit_json_error, hint, log, long_running, setup

EXIT_OK, EXIT_ERROR, EXIT_USAGE = 0, 1, 2


def writer_lock(cfg) -> state.Lock:
    """The lock that every command writing tracks.json or dates.json holds, so two of them never interleave."""
    return state.Lock(cfg.state, "catalog")


class UsageError(Exception):
    pass


def _version() -> str:
    from hist import __version__

    return __version__


class _Parser(argparse.ArgumentParser):
    """An ArgumentParser whose usage errors are JSON on standard error when --json is among the arguments."""

    json_requested = False

    def error(self, message: str):
        if _Parser.json_requested:
            emit_json_error(message, "usage")
            raise SystemExit(EXIT_USAGE)
        super().error(message)


# ----------------------------------------------------------------- commands


def cmd_init(args, home: Path) -> int:
    cfg = config_mod.Config(home=home)
    if args.source:
        src = Path(args.source).expanduser()
        if not (src / "tracks.json").exists():
            raise UsageError(f"{src} is not a catalog (no tracks.json)")
        if catalog.read_records(cfg) and not args.force:
            raise UsageError(f"{home} already holds a catalog; use --force to replace it")
        home.mkdir(parents=True, exist_ok=True)
        for name in ("config.toml", "tracks.json", "dates.json"):
            if (src / name).exists():
                shutil.copy2(src / name, home / name)
        if (src / "covers").is_dir():
            shutil.copytree(src / "covers", home / "covers", dirs_exist_ok=True)
        cfg = config_mod.load(home)
        problems = catalog.check(cfg)
        for p in problems:
            log.warning(p)
        records = catalog.read_records(cfg)
        agent.write_guides(home)
        log.info(
            f"Copied the catalog from {src} to {home} ({len(records)} tracks, "
            f"{len(catalog.albums(cfg))} albums)" + (f"; {len(problems)} problems" if problems else "")
        )
        return EXIT_ERROR if problems else EXIT_OK
    home.mkdir(parents=True, exist_ok=True)
    (home / "covers").mkdir(exist_ok=True)
    if not cfg.config_file.exists():
        cfg.config_file.write_text(config_mod.TEMPLATE, encoding="utf-8")
    if not cfg.tracks_file.exists():
        state.write_json(cfg.tracks_file, {"format": catalog.FORMAT, "tracks": []})
    if not cfg.dates_file.exists():
        state.write_json(cfg.dates_file, {"entries": []})
    agent.write_guides(home)
    log.info(f"Initialized {home}. Edit {cfg.config_file}, then run 'hist doctor'.")
    return EXIT_OK


def cmd_doctor(args, cfg) -> int:
    from hist import doctor

    return doctor.run(cfg, args.json)


def cmd_agent_help(args, home: Path) -> int:
    if args.json:
        sys.stdout.write(agent.guide_json())
    else:
        sys.stdout.write(agent.agents_md())
    return EXIT_OK


def cmd_status(args, cfg) -> int:
    if args.music:
        proc.require_macos("status --music")
    from hist import status
    from hist.music_app import MusicApp

    return status.run(cfg, MusicApp() if args.music else None, args.json)


def convert_options(args):
    from hist import convert

    return convert.Options(only=args.only or "", keep_flac=args.keep_flac, dry_run=getattr(args, "dry_run", False))


def cmd_convert(args, cfg) -> int:
    from hist import convert

    options = convert_options(args)
    if options.dry_run:
        convert.run_once(cfg, options)
        return EXIT_OK
    with state.Lock(cfg.state, "convert"):
        result = convert.run_once(cfg, options)
    for line in result.low_disk:
        log.warning(f"low disk space: {line}; skipped")
    if not result.converted:
        log.info("Nothing to convert: no complete download of an unconverted album was found.")
    return EXIT_OK


def cmd_watch(args, cfg) -> int:
    if not args.convert_only:
        proc.require_macos("hist watch (without --convert-only)")
    from hist import watch

    stopper = runtime.Stopper().install()
    with state.Lock(cfg.state, "convert"):
        long_running(Path(args.log).expanduser() if args.log else cfg.state / "logs" / "watch.log")
        runtime.keep_awake()
        return watch.run(cfg, convert_options(args), stopper, interval=args.interval, convert_only=args.convert_only)


def cmd_stop(args, cfg) -> int:
    pid = state.holder(cfg.state, "convert")
    if not pid:
        print("Nothing is running.")
        return EXIT_OK
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print("Nothing is running.")
        return EXIT_OK
    except PermissionError:
        raise HistError(f"hist (pid {pid}) belongs to another user and cannot be stopped") from None
    print(f"Asked hist (pid {pid}) to stop after the current album.")
    return EXIT_OK


def entry_label(entry: dict) -> str:
    return f"{entry['date']:%Y-%m-%d}  {entry['kind']:6}  {entry['path']}"


def dates_list(entries: list, root: Path, as_json: bool = False) -> int:
    if as_json:
        emit_json(
            {
                "entries": [
                    {
                        "kind": e["kind"],
                        "path": e["path"],
                        "date": f"{e['date']:%Y-%m-%d}",
                        "in_library": (root / e["path"]).is_dir(),
                    }
                    for e in entries
                ]
            }
        )
        return EXIT_OK
    for e in entries:
        here = (root / e["path"]).is_dir()
        print(f"{entry_label(e)}: " + ("in the library" if here else "not in the library"))
    return EXIT_OK


def dates_script(entries: list, root: Path) -> int:
    for e in entries:
        print(dates.shell_line(e, root))
    return EXIT_OK


def dates_check(entries: list, root: Path, whole_library: bool, as_json: bool = False) -> int:
    if entries:
        proc.require_macos("hist dates check")
    folders = files = 0
    wrong, covered = [], set()
    for e in entries:
        if not (root / e["path"]).is_dir():
            continue
        bad = {item for item, _, _ in dates.check(e, root)}
        for item in dates.items(e, root):
            if item in bad:
                wrong.append(str(item.relative_to(root)))
            if item.is_dir():
                folders += 1
            else:
                files += 1
                covered.add(str(item))
    uncovered = None
    if whole_library:
        in_library = {os.path.join(d, f) for d, _, names in os.walk(root) for f in names if f.endswith(".m4a")}
        uncovered = len(in_library - covered)
    if as_json:
        emit_json({"ok": not wrong, "folders": folders, "files": files, "wrong": wrong, "uncovered": uncovered})
        return EXIT_ERROR if wrong else EXIT_OK
    for w in wrong:
        print(f"  wrong date: {w}")
    print(
        f"Checked {folders} folders and {files} files: "
        + (f"{len(wrong)} with a wrong date" if wrong else "no mismatches")
    )
    if uncovered:
        log.warning(f"{uncovered} .m4a files of the library are not covered by dates.json")
    return EXIT_ERROR if wrong else EXIT_OK


def dates_apply(entries: list, root: Path, dry_run: bool) -> int:
    if entries and not dry_run:
        proc.require_macos("hist dates apply")
    failed = done = skipped = 0
    for e in entries:
        if not (root / e["path"]).is_dir():
            log.info(f"{entry_label(e)}: not in the library")
            skipped += 1
            continue
        if dry_run:
            log.info(f"{entry_label(e)}: would set {len(dates.items(e, root))} items")
            continue
        try:
            dates.apply(e, root)
        except dates.DatesError as error:
            log.error(str(error))
            failed += 1
            continue
        wrong = dates.check(e, root)
        done += 1
        failed += bool(wrong)
        log.info(
            f"{entry_label(e)}: {len(dates.items(e, root))} items set"
            + (f", {len(wrong)} still differ" if wrong else "")
        )
    if not dry_run:
        log.info(f"Entries set: {done}, not in the library: {skipped}, problems: {failed}")
    return EXIT_ERROR if failed else EXIT_OK


def dates_set(args, cfg) -> int:
    if len(args.operands) != 2:
        raise UsageError("usage: hist dates set PATH DATE [--kind album|artist]")
    path, date = args.operands
    with writer_lock(cfg):
        done = dates.set_entry(cfg.dates_file, path, date, args.kind, state.Backup(cfg.state, "dates-set"))
    if args.json:
        emit_json({"action": "set", **done})
    elif done["previous"] == done["date"]:
        log.info(f"The {done['kind']} entry {path} already has the date {date}.")
    else:
        log.info(
            f"Set the {done['kind']} entry {path} to {date}"
            + (f" (was {done['previous']})" if done["previous"] else "")
            + ". Run 'hist dates apply' to set the dates in the library."
        )
    return EXIT_OK


def dates_unset(args, cfg) -> int:
    if len(args.operands) != 1:
        raise UsageError("usage: hist dates unset PATH")
    with writer_lock(cfg):
        gone = dates.unset_entry(cfg.dates_file, args.operands[0], state.Backup(cfg.state, "dates-unset"))
    if args.json:
        emit_json({"action": "unset", "removed": gone})
    else:
        log.info(f"Removed {len(gone)} dates entr{'y' if len(gone) == 1 else 'ies'} for {args.operands[0]}.")
    return EXIT_OK


def cmd_dates(args, cfg) -> int:
    if args.action in ("set", "unset"):
        return dates_set(args, cfg) if args.action == "set" else dates_unset(args, cfg)
    if args.operands:
        raise UsageError(f"'hist dates {args.action}' takes no arguments (see --only)")
    if args.json and args.action not in ("list", "check"):
        raise UsageError("--json is available for 'hist dates list', 'check', 'set' and 'unset' only")
    entries = dates.select(dates.entries(cfg.dates_file), args.only)
    if args.action == "list":
        return dates_list(entries, cfg.library, args.json)
    if args.action == "script":
        return dates_script(entries, cfg.library)
    if args.action == "check":
        return dates_check(entries, cfg.library, whole_library=not args.only, as_json=args.json)
    return dates_apply(entries, cfg.library, args.dry_run)


def cmd_verify(args, cfg) -> int:
    if args.music:
        proc.require_macos("verify --music")
    from hist import verify
    from hist.music_app import MusicApp

    roots = [Path(p).expanduser() for p in args.path] if args.path else [cfg.library]
    if args.downloads:
        roots += list(cfg.sources)
    music = MusicApp() if args.music else None
    if not args.json:
        return verify.run(cfg, roots, args.allow_missing, not args.no_decode, music)
    lines = []

    class Capture(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())

    capture = Capture()
    log.addHandler(capture)
    quiet = [h for h in log.handlers if h is not capture]
    levels = [(h, h.level) for h in quiet]
    for h in quiet:
        h.setLevel(logging.WARNING)
    try:
        code = verify.run(cfg, roots, args.allow_missing, not args.no_decode, music)
    finally:
        log.removeHandler(capture)
        for h, level in levels:
            h.setLevel(level)
    emit_json({"ok": code == 0, "lines": lines})
    return code


def album_tracks(cfg, args) -> tuple:
    records = catalog.read_records(cfg)
    album = catalog.select_album(records, args.album, args.exact)
    return album, catalog.pick_records(records, album, args.disc, args.track)


def folder_of(album: dict, library: Path) -> str:
    """The folder of an album relative to the library, or as stored when it lies outside the library."""
    folder = Path(album["tracks"][0].path).parent
    try:
        return str(folder.relative_to(library))
    except ValueError:
        return str(folder)


def catalog_list(args, cfg) -> int:
    found = catalog.albums(cfg)
    if args.json:
        emit_json(
            {
                "albums": [
                    {
                        "name": a["name"],
                        "album_artist": a["tracks"][0].tags.get("ItemList:AlbumArtist", ""),
                        "release": a["release"],
                        "tracks": len(a["tracks"]),
                        "folder": folder_of(a, cfg.library),
                    }
                    for a in found
                ]
            }
        )
        return EXIT_OK
    for album in found:
        t = album["tracks"][0].tags
        print(
            f"{album['release']}  {album['name'][:52]:52s}  {len(album['tracks']):3d}  "
            f"{t.get('ItemList:AlbumArtist', '')}"
        )
    return EXIT_OK


def catalog_show(args, cfg) -> int:
    album, picked = album_tracks(cfg, args)
    if args.json:
        emit_json(
            {
                "album": album,
                "tracks": [
                    {
                        "file": r["file"],
                        "disc": catalog.record_number(r)[0],
                        "track": catalog.record_number(r)[1],
                        "tags": r["tags"],
                        "blobs": r["blobs"],
                    }
                    for r in picked
                ],
            }
        )
    elif args.track is not None:
        for r in picked:
            print(f"file: {r['file']}")
            for tag, value in r["tags"].items():
                print(f"{tag}: {value}")
            for tag, value in r["blobs"].items():
                print(f"{tag}: covers/{value[0]}")
    else:
        print(album)
        for r in picked:
            disc, number = catalog.record_number(r)
            print(f"  {disc}-{number:02d}  {r['tags'].get('ItemList:Title', '')}")
    return EXIT_OK


def catalog_set(args, cfg) -> int:
    setting = args.action == "set"
    with writer_lock(cfg):
        album, changed, n = catalog.set_tag(
            cfg, args.album, args.tag, args.value if setting else None, args.disc, args.track, args.exact
        )
    log.info(
        f"{album}: {catalog.short_tag(args.tag)} {'set' if setting else 'removed'} on {changed} of "
        f"{n} tracks" + (" (the previous tracks.json is kept in state/backups)" if changed else "")
    )
    if changed:
        hint("hist retag PATH --apply   (the files keep their old tags until then)")
    return EXIT_OK


def catalog_remove(args, cfg) -> int:
    with writer_lock(cfg):
        removed = catalog.remove_album(cfg, args.album, dry_run=args.dry_run, exact=args.exact)
    verb = "Would remove" if args.dry_run else "Removed"
    log.info(
        f"{verb} {removed['album']} from the catalog: {removed['tracks']} tracks, "
        f"{len(removed['dates'])} dates entries, "
        f"{len(removed['covers'])} covers"
    )
    for path in removed["dates"]:
        log.info(f"  dates entry: {path}")
    for digest in removed["covers"]:
        log.info(f"  cover: covers/{digest}")
    if not args.dry_run:
        log.info("The previous files are kept in state/backups. The library and the Music app were not changed.")
    return EXIT_OK


def catalog_undo(args, cfg) -> int:
    with writer_lock(cfg):
        done = catalog.undo(cfg, dry_run=args.dry_run)
    if args.json:
        emit_json(done)
        return EXIT_OK
    verb = "Would restore" if args.dry_run else "Restored"
    if done["restored"]:
        log.info(f"{verb} {', '.join(done['restored'])} from state/backups/{done['from']}")
    if done["removed"]:
        log.info(
            f"{'Would remove' if args.dry_run else 'Removed'} {', '.join(done['removed'])} (it did not exist then)"
        )
    if done["covers"]:
        log.info(f"  {len(done['covers'])} covers {'would be' if args.dry_run else 'were'} put back into covers/")
    if done["backup"]:
        log.info(f"The files it replaced are kept in {done['backup']}; run 'hist catalog undo' again to redo.")
    if not args.dry_run:
        hint("hist retag PATH --apply   (the files keep their tags until then)")
    return EXIT_OK


def catalog_add(args, cfg) -> int:
    spec = catalog.read_spec(Path(args.spec).expanduser())
    with writer_lock(cfg):
        n = catalog.add_spec(cfg, spec, Path(args.source).expanduser(), dry_run=args.dry_run)
    log.info(("Would add " if args.dry_run else "Added ") + f"{spec['album']} ({n} tracks)")
    return EXIT_OK


def catalog_check(args, cfg) -> int:
    problems = catalog.check(cfg)
    if args.json:
        try:
            tracks = len(catalog.read_records(cfg))
        except (HistError, ValueError, KeyError):
            tracks = 0
        emit_json({"ok": not problems, "tracks": tracks, "problems": problems})
        return EXIT_ERROR if problems else EXIT_OK
    for p in problems:
        log.info(p)
    log.info(
        f"{len(catalog.read_records(cfg))} tracks: " + (f"{len(problems)} problems" if problems else "no problems")
    )
    return EXIT_ERROR if problems else EXIT_OK


def catalog_import(args, cfg) -> int:
    with writer_lock(cfg):
        n, no_disc = catalog.import_library(cfg, Path(args.folder).expanduser())
    log.info(f"Imported the tags of {n} files into {cfg.tracks_file}")
    if no_disc:
        log.warning(f"{no_disc} tracks have no DiskNumber; set one ('1 of 1' or 'n of N') with 'hist catalog set'")
    return EXIT_OK


def print_edit_report(report: dict) -> None:
    for c in report["changes"]:
        log.info(f"~ {c['file']}")
        for d in c["changes"]:
            before = "<none>" if d["before"] is None else d["before"]
            after = "<removed>" if d["after"] is None else d["after"]
            log.info(f"    {d['tag']}: {before} -> {after}")
    log.info(
        f"{report['operations']} operations, {report['tracks_changed']} tracks "
        + ("would change" if report["dry_run"] else "changed")
        + (
            "; nothing was written."
            if report["dry_run"]
            else f" (the previous tracks.json is kept in {report['backup']})."
            if report["backup"]
            else "."
        )
    )


def catalog_edit(args, cfg) -> int:
    from hist import edit

    if args.retag and args.json:
        raise UsageError("--retag cannot be combined with --json; run 'hist retag' afterwards")
    if args.retag and args.dry_run:
        raise UsageError("--retag cannot be combined with --dry-run")
    if args.file == "-" and sys.stdin.isatty():
        raise UsageError(
            "no operations given: pass FILE, or pipe a JSON array to standard input (see 'hist agent-help')"
        )
    operations = edit.read_operations(args.file, sys.stdin)
    if args.dry_run:
        report = edit.run(cfg, operations, True, args.exact)
    else:
        with writer_lock(cfg):
            report = edit.run(cfg, operations, False, args.exact)
    report["next"] = next_steps(cfg, report)
    if args.json:
        emit_json(report)
        return EXIT_OK
    print_edit_report(report)
    if not report["changes"] or report["dry_run"]:
        return EXIT_OK
    if args.retag:
        from hist import retag

        folders = [cfg.library / f for f in report["folders"] if (cfg.library / f).is_dir()]
        if not folders:
            log.info("None of the changed albums is in the library; nothing to retag.")
            return EXIT_OK
        return retag.run(cfg, folders, True, "", False, False)
    for step in report["next"]:
        hint(step)
    return EXIT_OK


def next_steps(cfg, report: dict) -> list:
    """The commands to run after an edit (in --json output: the field "next")."""
    if not report["changes"]:
        return []
    if report["dry_run"]:
        return ["run the same command without --dry-run to apply the changes"]
    return [f"hist retag '{cfg.library / f}' --apply" for f in report["folders"]]


def catalog_cover(args, cfg) -> int:
    with writer_lock(cfg):
        done = catalog.set_cover(cfg, args.album, Path(args.image), args.exact)
    log.info(
        f"{done['album']}: the cover is covers/{done['cover']} on {done['tracks']} tracks ({done['changed']} changed)"
    )
    if done["changed"]:
        hint("hist retag PATH --apply   (the files keep their old cover until then)")
    return EXIT_OK


def catalog_export(args, cfg) -> int:
    out = Path(args.output).expanduser() if args.output else None
    spec, warnings = catalog.export_spec(cfg, args.album, args.exact, out)
    text = json.dumps(spec, ensure_ascii=False, indent=1) + "\n"
    if out:
        out.write_text(text, encoding="utf-8")
        log.info(f"Wrote the spec of {spec['album']} to {out}")
    else:
        sys.stdout.write(text)
    for w in warnings:
        log.warning(w)
    return EXIT_OK


CATALOG_ACTIONS = {
    "list": catalog_list,
    "show": catalog_show,
    "set": catalog_set,
    "unset": catalog_set,
    "remove": catalog_remove,
    "add": catalog_add,
    "check": catalog_check,
    "import": catalog_import,
    "edit": catalog_edit,
    "cover": catalog_cover,
    "export": catalog_export,
    "undo": catalog_undo,
}


def cmd_catalog(args, cfg) -> int:
    action = CATALOG_ACTIONS.get(args.action)
    if action is None:
        raise UsageError(f"unknown catalog action {args.action}")
    return action(args, cfg)


def cmd_retag(args, cfg) -> int:
    from hist import retag

    return retag.run(
        cfg, [Path(p).expanduser() for p in args.paths], args.apply, args.fields or "", args.prune, args.verbose_list
    )


def cmd_refresh(args, cfg) -> int:
    proc.require_macos("hist refresh")
    from hist.music_app import MusicApp

    music = MusicApp()
    records = catalog.read_records(cfg)
    name = catalog.select_album(records, args.album, args.exact)
    rows = music.tracks(name)
    if not rows:
        log.error(f"the Music app lists no tracks of '{name}'")
        return EXIT_ERROR
    music.refresh([r["id"] for r in rows])
    after = music.tracks(name)
    log.info(f"Refreshed {len(rows)} tracks of {name}; the Music app now lists {len(after)}.")
    return EXIT_OK if len(after) == len(rows) else EXIT_ERROR


def cmd_evacuate(args, cfg) -> int:
    proc.require_macos("hist evacuate")
    from hist import evacuate
    from hist.music_app import MusicApp

    return evacuate.run(cfg, MusicApp(), args.album or "", args.dry_run)


def cmd_store_entries(args, cfg) -> int:
    proc.require_macos("hist store-entries")
    from hist import store
    from hist.music_app import MusicApp

    return store.run(cfg, MusicApp(), args.delete)


# ------------------------------------------------------------------ parser


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="hist",
        description="Rebuild an Apple Music library on macOS from FLAC downloads with exact, verified tags.",
        epilog="Run 'hist <command> --help' for the options of a command. Scripts and AI agents: read commands with "
        "--json, change tags with 'hist catalog edit FILE --dry-run' and then without --dry-run, and run "
        "'hist agent-help' for the guide.",
    )
    parser.add_argument("--version", action="version", version=f"hist {_version()}")
    parser.add_argument(
        "--home", metavar="DIR", help="catalog folder (default: $HISTORY_HOME or ~/Library/Application Support/HIStory)"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="print warnings and errors only")
    parser.add_argument("-v", "--verbose", action="store_true", help="print more detail")
    sub = parser.add_subparsers(dest="command", metavar="<command>", title="commands")

    def add(name, func, help_text, **kw):
        p = sub.add_parser(name, help=help_text, description=help_text[0].upper() + help_text[1:] + ".", **kw)
        p.set_defaults(func=func)
        return p

    p = add("init", cmd_init, "create the catalog folder, or copy an existing catalog into it")
    p.add_argument(
        "--from", dest="source", metavar="DIR", help="copy this catalog (config.toml, tracks.json, covers/, dates.json)"
    )
    p.add_argument("--force", action="store_true", help="replace a catalog that already holds tracks")

    p = add("doctor", cmd_doctor, "check the tools, the configuration and the catalog")
    p.add_argument("--json", action="store_true", help="print JSON instead of text")

    p = add("agent-help", cmd_agent_help, "print the guide for AI agents and scripts")
    p.add_argument("--json", action="store_true", help="print the guide as JSON instead of Markdown")

    p = add("status", cmd_status, "show how far each album has come, oldest release first")
    p.add_argument("--music", action="store_true", help="also count each album's tracks in the Music app")
    p.add_argument("--json", action="store_true", help="print JSON instead of text")

    def convert_args(p):
        p.add_argument("--only", metavar="TEXT", help="only albums whose name contains TEXT")
        p.add_argument("--keep-flac", action="store_true", help="keep the FLAC files after the checks")
        p.add_argument(
            "--source",
            action="append",
            metavar="DIR",
            help="download folder instead of the configured ones (repeatable)",
        )

    p = add("convert", cmd_convert, "convert every complete download once (tags, ALAC, checks)")
    convert_args(p)
    p.add_argument("--dry-run", action="store_true", help="show how the files would be paired; write nothing")

    p = add(
        "watch",
        cmd_watch,
        "convert downloads as they complete and set the dates of albums you add to the "
        "Music app; ends when every album is converted and in the library",
    )
    convert_args(p)
    p.add_argument(
        "--convert-only", action="store_true", help="do not watch the library; end when every album is converted"
    )
    p.add_argument("--interval", type=float, default=10, metavar="SECONDS", help="time between looks (default 10)")
    p.add_argument("--log", metavar="FILE", help="log file (default: <home>/state/logs/watch.log)")

    add("stop", cmd_stop, "ask a running watch or convert to stop after the current album")

    p = add("dates", cmd_dates, "list, set or check the dates of the library's folders and files, or edit dates.json")
    p.add_argument("action", choices=("list", "apply", "check", "script", "set", "unset"))
    p.add_argument("operands", nargs="*", metavar="ARG", help="(set) PATH DATE; (unset) PATH")
    p.add_argument(
        "--kind",
        choices=("album", "artist"),
        help="(set) the entry's kind (default: from the path: Artist is artist, Artist/Album is album)",
    )
    p.add_argument("--json", action="store_true", help="(list, set, unset) print JSON instead of text")
    p.add_argument("--only", default="", metavar="TEXT", help="only entries whose path contains TEXT")
    p.add_argument("--dry-run", action="store_true", help="(apply) show what would be set")

    p = add("verify", cmd_verify, "check the library's files (and optionally the Music app) against the catalog")
    p.add_argument("--music", action="store_true", help="also check the Music app's entries")
    p.add_argument("--downloads", action="store_true", help="also check converted files in the download folders")
    p.add_argument(
        "--path", action="append", metavar="DIR", help="check this folder instead of the library (repeatable)"
    )
    p.add_argument("--allow-missing", action="store_true", help="do not fail because tracks are missing")
    p.add_argument("--no-decode", action="store_true", help="skip decoding every file")
    p.add_argument("--json", action="store_true", help='print {"ok": ..., "lines": [...]} instead of text')

    p = add("catalog", cmd_catalog, "list, show, edit, add to, remove from, undo changes to and check the catalog")
    actions = p.add_subparsers(dest="action", metavar="<action>", required=True)

    def album_args(a, track=False):
        a.add_argument("--exact", action="store_true", help="ALBUM is the album's exact name, not text it contains")
        if track:
            a.add_argument("--disc", type=int)
            a.add_argument("--track", type=int)

    a = actions.add_parser("list", help="list the albums, oldest release first")
    a.add_argument("--json", action="store_true", help="print JSON instead of text")
    a = actions.add_parser("show", help="show the tracks of an album, or every tag of one track")
    a.add_argument("album", help="text contained in the album name")
    album_args(a, track=True)
    a.add_argument("--json", action="store_true", help="print every tag of the selected tracks as JSON")
    a = actions.add_parser("set", help="set a tag on an album's tracks (or one track)")
    a.add_argument("album")
    a.add_argument("tag", help="tag name, e.g. Genre or ItemList:Genre")
    a.add_argument("value")
    album_args(a, track=True)
    a = actions.add_parser("unset", help="remove a tag from an album's tracks (or one track)")
    a.add_argument("album")
    a.add_argument("tag")
    album_args(a, track=True)
    a = actions.add_parser("edit", help="apply a JSON array of set and unset operations in one step")
    a.add_argument(
        "file", nargs="?", default="-", metavar="FILE", help="the operations (default or '-': standard input)"
    )
    a.add_argument("--dry-run", action="store_true", help="show the changes per track; write nothing")
    a.add_argument(
        "--retag",
        action="store_true",
        help="then write the new tags into the albums' files in the library ('hist retag --apply')",
    )
    a.add_argument("--exact", action="store_true", help="every album is an exact name, not text it contains")
    a.add_argument("--json", action="store_true", help="print the changes as JSON")
    a = actions.add_parser("cover", help="make an image the cover of every track of an album")
    a.add_argument("album", help="text contained in the album name")
    a.add_argument("image", help="a JPEG or PNG file")
    album_args(a)
    a = actions.add_parser("export", help="write an album as a spec file that 'catalog add' accepts")
    a.add_argument("album", help="text contained in the album name")
    a.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="write the spec (and a copy of the cover) here instead of to standard output",
    )
    album_args(a)
    a = actions.add_parser("add", help="add an album from a spec file and its downloaded FLAC folder")
    a.add_argument("spec")
    a.add_argument("--from", dest="source", required=True, metavar="DIR", help="the album's FLAC folder")
    a.add_argument("--dry-run", action="store_true")
    a = actions.add_parser(
        "remove",
        help="remove an album from the catalog (after you removed it from the Music app); the library is not touched",
    )
    a.add_argument("album", help="text contained in the album name")
    a.add_argument("--dry-run", action="store_true", help="show what would be removed")
    album_args(a)
    a = actions.add_parser("undo", help="restore the files of the newest backup (a second undo redoes it)")
    a.add_argument("--dry-run", action="store_true", help="show what would be restored")
    a.add_argument("--json", action="store_true", help="print JSON instead of text")
    a = actions.add_parser("check", help="check the catalog files for consistency")
    a.add_argument("--json", action="store_true", help="print JSON instead of text")
    a = actions.add_parser("import", help="start an empty catalog from the tags of an existing library folder")
    a.add_argument("folder")

    p = add("retag", cmd_retag, "write the catalog's tags back into existing M4A files")
    p.add_argument("paths", nargs="+", metavar="PATH")
    p.add_argument("--apply", action="store_true", help="write the changes (default: only show them)")
    p.add_argument("--fields", metavar="LIST", help="only these tags, e.g. Genre,Composer")
    p.add_argument("--prune", action="store_true", help="also remove tags the catalog does not have")
    p.add_argument("--list-unmatched", dest="verbose_list", action="store_true", help="list files without a match")

    p = add("refresh", cmd_refresh, "make the Music app re-read the files of an album")
    p.add_argument("album", help="text contained in the album name")
    p.add_argument("--exact", action="store_true", help="ALBUM is the album's exact name, not text it contains")

    p = add("evacuate", cmd_evacuate, "move albums out of the library and remove their entries, to add them again")
    p.add_argument("--album", metavar="TEXT", help="only albums whose name contains TEXT")
    p.add_argument("--dry-run", action="store_true")

    p = add("store-entries", cmd_store_entries, "list, or delete, the Music app's entries of the store album")
    p.add_argument("--delete", action="store_true", help="delete the entries that still carry purchase data")
    return parser


def fail(args, message: str, code: str, status: int) -> int:
    """Report an error (as JSON on standard error with --json) and return the exit status."""
    if getattr(args, "json", False):
        emit_json_error(message, code)
    else:
        log.error(message)
    return status


def main(argv=None) -> int:
    parser = build_parser()
    _Parser.json_requested = "--json" in (sys.argv[1:] if argv is None else list(argv))
    args = parser.parse_args(argv)
    setup(verbose=args.verbose, quiet=args.quiet)
    if not args.command:
        parser.print_help()
        return EXIT_USAGE
    home = config_mod.resolve_home(args.home)
    try:
        if args.func is cmd_init:
            return cmd_init(args, home)
        if args.func is cmd_agent_help:
            return cmd_agent_help(args, home)
        if args.func is not cmd_doctor and not (home / "config.toml").exists() and not (home / "tracks.json").exists():
            raise config_mod.ConfigError(
                f"there is no catalog in {home}; run 'hist init' to create one, or name "
                "an existing one with --home DIR or the HISTORY_HOME variable"
            )
        cfg = config_mod.load(home, getattr(args, "source", None) if args.func in (cmd_convert, cmd_watch) else None)
        if (moved := state.migrate_backups(cfg.state)) and not getattr(args, "json", False):
            log.info(f"Moved {moved} old backups from state/history and state/snapshots to state/backups")
        return args.func(args, cfg)
    except UsageError as error:
        return fail(args, str(error), "usage", EXIT_USAGE)
    except config_mod.ConfigError as error:
        return fail(args, str(error), error.code, EXIT_USAGE)
    except runtime.Stopped as error:
        log.info("Stopped.")
        return error.exit_code
    except KeyboardInterrupt:
        sys.stderr.write("\n")
        log.info("Interrupted.")
        return 130
    except state.LockHeld as error:
        advice = (
            "; run 'hist stop' to stop it"
            if error.name == "convert"
            else "; wait for it to finish, then run the command again"
        )
        return fail(args, f"{error}{advice}", error.code, EXIT_ERROR)
    except proc.ToolError as error:
        return fail(args, f"{error}; run 'hist doctor'", error.code, EXIT_ERROR)
    except HistError as error:
        return fail(args, str(error), error.code, EXIT_ERROR)
    except (OSError, ValueError) as error:  # includes JSONDecodeError and UnicodeDecodeError
        if args.verbose:
            traceback.print_exc()
        return fail(args, str(error), "error", EXIT_ERROR)
