"""The 'hist' command line."""
import argparse
import os
import shutil
import signal
import sys
from pathlib import Path

from hist import __version__, catalog, config as config_mod, dates, proc, runtime, state
from hist.errors import HistError
from hist.log import log, long_running, setup

EXIT_OK, EXIT_ERROR, EXIT_USAGE = 0, 1, 2


class UsageError(Exception):
    pass


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
        log.info(f"Copied the catalog from {src} to {home} ({len(records)} tracks, "
                 f"{len(catalog.albums(cfg))} albums)" + (f"; {len(problems)} problems" if problems else ""))
        return EXIT_ERROR if problems else EXIT_OK
    home.mkdir(parents=True, exist_ok=True)
    (home / "covers").mkdir(exist_ok=True)
    if not cfg.config_file.exists():
        cfg.config_file.write_text(config_mod.TEMPLATE, encoding="utf-8")
    if not cfg.tracks_file.exists():
        state.write_json(cfg.tracks_file, {"format": catalog.FORMAT, "tracks": []})
    if not cfg.dates_file.exists():
        state.write_json(cfg.dates_file, {"entries": []})
    log.info(f"Initialized {home}. Edit {cfg.config_file}, then run 'hist doctor'.")
    return EXIT_OK


def cmd_doctor(args, cfg) -> int:
    from hist import doctor
    return doctor.run(cfg)


def cmd_status(args, cfg) -> int:
    from hist import status
    from hist.music_app import MusicApp
    return status.run(cfg, MusicApp() if args.music else None)


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
    from hist import runtime, watch
    stopper = runtime.Stopper().install()
    with state.Lock(cfg.state, "convert"):
        long_running(Path(args.log).expanduser() if args.log else cfg.state / "logs" / "watch.log")
        runtime.keep_awake()
        return watch.run(cfg, convert_options(args), stopper, interval=args.interval, convert_only=args.convert_only)


def cmd_stop(args, cfg) -> int:
    pid = state.holder(cfg.state, "convert")
    if not pid or pid < 0:
        log.info("Nothing is running.")
        return EXIT_OK
    os.kill(pid, signal.SIGTERM)
    log.info(f"Asked hist (pid {pid}) to stop after the current album.")
    return EXIT_OK


def entry_label(entry: dict) -> str:
    return f"{entry['date']:%Y-%m-%d}  {entry['kind']:6}  {entry['path']}"


def dates_list(entries: list, root: Path) -> int:
    for e in entries:
        here = (root / e["path"]).is_dir()
        log.info(f"{entry_label(e)}: " + ("in the library" if here else "not in the library"))
    return EXIT_OK


def dates_script(entries: list, root: Path) -> int:
    for e in entries:
        print(dates.shell_line(e, root))
    return EXIT_OK


def dates_check(entries: list, root: Path, whole_library: bool) -> int:
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
    for w in wrong:
        log.info(f"  wrong date: {w}")
    log.info(f"Checked {folders} folders and {files} files: "
             + (f"{len(wrong)} with a wrong date" if wrong else "no mismatches"))
    if whole_library:
        in_library = {os.path.join(d, f) for d, _, names in os.walk(root) for f in names if f.endswith(".m4a")}
        uncovered = len(in_library - covered)
        if uncovered:
            log.warning(f"{uncovered} .m4a files of the library are not covered by dates.json")
    return EXIT_ERROR if wrong else EXIT_OK


def dates_apply(entries: list, root: Path, dry_run: bool) -> int:
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
        log.info(f"{entry_label(e)}: {len(dates.items(e, root))} items set"
                 + (f", {len(wrong)} still differ" if wrong else ""))
    if not dry_run:
        log.info(f"Entries set: {done}, not in the library: {skipped}, problems: {failed}")
    return EXIT_ERROR if failed else EXIT_OK


def cmd_dates(args, cfg) -> int:
    entries = dates.select(dates.entries(cfg.dates_file), args.only)
    if args.action == "list":
        return dates_list(entries, cfg.library)
    if args.action == "script":
        return dates_script(entries, cfg.library)
    if args.action == "check":
        return dates_check(entries, cfg.library, whole_library=not args.only)
    return dates_apply(entries, cfg.library, args.dry_run)


def cmd_verify(args, cfg) -> int:
    from hist import verify
    from hist.music_app import MusicApp
    roots = [Path(p).expanduser() for p in args.path] if args.path else [cfg.library]
    if args.downloads:
        roots += list(cfg.sources)
    return verify.run(cfg, roots, args.allow_missing, not args.no_decode, MusicApp() if args.music else None)


def cmd_catalog(args, cfg) -> int:
    action = args.action
    if action == "list":
        for album in catalog.albums(cfg):
            t = album["tracks"][0].tags
            print(f"{album['release']}  {album['name'][:52]:52s}  {len(album['tracks']):3d}  "
                  f"{t.get('ItemList:AlbumArtist', '')}")
        return EXIT_OK
    if action == "show":
        records = catalog.read_records(cfg)
        album = catalog.select_album(records, args.album)
        picked = catalog.pick_records(records, album, args.disc, args.track)
        if args.track is not None:
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
    if action in ("set", "unset"):
        album, changed, n = catalog.set_tag(cfg, args.album, args.tag, args.value if action == "set" else None,
                                            args.disc, args.track)
        log.info(f"{album}: {catalog.short_tag(args.tag)} {'set' if action == 'set' else 'removed'} on {changed} of "
                 f"{n} tracks" + (" (the previous tracks.json is kept in state/backups)" if changed else ""))
        if changed:
            log.info("Converted files keep their old tags until 'hist retag PATH --apply' is run.")
        return EXIT_OK
    if action == "remove":
        removed = catalog.remove_album(cfg, args.album, dry_run=args.dry_run)
        verb = "Would remove" if args.dry_run else "Removed"
        log.info(f"{verb} {removed['album']} from the catalog: {removed['tracks']} tracks, "
                 f"{len(removed['dates'])} dates entries, "
                 f"{len(removed['covers'])} covers")
        for path in removed["dates"]:
            log.info(f"  dates entry: {path}")
        for digest in removed["covers"]:
            log.info(f"  cover: covers/{digest}")
        if not args.dry_run:
            log.info("The previous files are kept in state/backups. The library and the Music app were not changed.")
        return EXIT_OK
    if action == "add":
        spec = catalog.read_spec(Path(args.spec).expanduser())
        n = catalog.add_spec(cfg, spec, Path(args.source).expanduser(), dry_run=args.dry_run)
        log.info(("Would add " if args.dry_run else "Added ") + f"{spec['album']} ({n} tracks)")
        return EXIT_OK
    if action == "check":
        problems = catalog.check(cfg)
        for p in problems:
            log.info(p)
        log.info(f"{len(catalog.read_records(cfg))} tracks: " + (f"{len(problems)} problems" if problems else "no problems"))
        return EXIT_ERROR if problems else EXIT_OK
    if action == "import":
        n, no_disc = catalog.import_library(cfg, Path(args.folder).expanduser())
        log.info(f"Imported the tags of {n} files into {cfg.tracks_file}")
        if no_disc:
            log.warning(f"{no_disc} tracks have no DiskNumber; set one ('1 of 1' or 'n of N') with 'hist catalog set'")
        return EXIT_OK
    raise UsageError(f"unknown catalog action {action}")


def cmd_retag(args, cfg) -> int:
    from hist import retag
    return retag.run(cfg, [Path(p).expanduser() for p in args.paths], args.apply, args.fields or "", args.prune,
                     args.verbose_list)


def cmd_refresh(args, cfg) -> int:
    from hist.music_app import MusicApp
    music = MusicApp()
    records = catalog.read_records(cfg)
    name = catalog.select_album(records, args.album)
    rows = music.tracks(name)
    if not rows:
        log.error(f"the Music app lists no tracks of '{name}'")
        return EXIT_ERROR
    music.refresh([r["id"] for r in rows])
    after = music.tracks(name)
    log.info(f"Refreshed {len(rows)} tracks of {name}; the Music app now lists {len(after)}.")
    return EXIT_OK if len(after) == len(rows) else EXIT_ERROR


def cmd_evacuate(args, cfg) -> int:
    from hist import evacuate
    from hist.music_app import MusicApp
    return evacuate.run(cfg, MusicApp(), args.album or "", args.dry_run)


def cmd_store_entries(args, cfg) -> int:
    from hist import store
    from hist.music_app import MusicApp
    return store.run(cfg, MusicApp(), args.delete)


# ------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hist",
        description="Rebuild an Apple Music library on macOS from FLAC downloads with exact, verified tags.",
        epilog="Run 'hist <command> --help' for the options of a command.")
    parser.add_argument("--version", action="version", version=f"hist {__version__}")
    parser.add_argument("--home", metavar="DIR", help="catalog folder (default: $HISTORY_HOME or "
                                                       "~/Library/Application Support/HIStory)")
    parser.add_argument("-q", "--quiet", action="store_true", help="print warnings and errors only")
    parser.add_argument("-v", "--verbose", action="store_true", help="print more detail")
    sub = parser.add_subparsers(dest="command", metavar="<command>", title="commands")

    def add(name, func, help_text, **kw):
        p = sub.add_parser(name, help=help_text, description=help_text[0].upper() + help_text[1:] + ".", **kw)
        p.set_defaults(func=func)
        return p

    p = add("init", cmd_init, "create the catalog folder, or copy an existing catalog into it")
    p.add_argument("--from", dest="source", metavar="DIR", help="copy this catalog (config.toml, tracks.json, "
                                                                "covers/, dates.json)")
    p.add_argument("--force", action="store_true", help="replace a catalog that already holds tracks")

    add("doctor", cmd_doctor, "check the tools, the configuration and the catalog")

    p = add("status", cmd_status, "show how far each album has come, oldest release first")
    p.add_argument("--music", action="store_true", help="also count each album's tracks in the Music app")

    def convert_args(p):
        p.add_argument("--only", metavar="TEXT", help="only albums whose name contains TEXT")
        p.add_argument("--keep-flac", action="store_true", help="keep the FLAC files after the checks")
        p.add_argument("--source", action="append", metavar="DIR", help="download folder instead of the "
                                                                         "configured ones (repeatable)")

    p = add("convert", cmd_convert, "convert every complete download once (tags, ALAC, checks)")
    convert_args(p)
    p.add_argument("--dry-run", action="store_true", help="show how the files would be paired; write nothing")

    p = add("watch", cmd_watch, "convert downloads as they complete and set the dates of albums you add to the "
                                "Music app; ends when every album is converted and in the library")
    convert_args(p)
    p.add_argument("--convert-only", action="store_true", help="do not watch the library; end when every album "
                                                               "is converted")
    p.add_argument("--interval", type=float, default=10, metavar="SECONDS", help="time between looks (default 10)")
    p.add_argument("--log", metavar="FILE", help="log file (default: <home>/state/logs/watch.log)")

    add("stop", cmd_stop, "ask a running watch or convert to stop after the current album")

    p = add("dates", cmd_dates, "list, set or check the dates of the library's folders and files")
    p.add_argument("action", choices=("list", "apply", "check", "script"))
    p.add_argument("--only", default="", metavar="TEXT", help="only entries whose path contains TEXT")
    p.add_argument("--dry-run", action="store_true", help="(apply) show what would be set")

    p = add("verify", cmd_verify, "check the library's files (and optionally the Music app) against the catalog")
    p.add_argument("--music", action="store_true", help="also check the Music app's entries")
    p.add_argument("--downloads", action="store_true", help="also check converted files in the download folders")
    p.add_argument("--path", action="append", metavar="DIR", help="check this folder instead of the library "
                                                                   "(repeatable)")
    p.add_argument("--allow-missing", action="store_true", help="do not fail because tracks are missing")
    p.add_argument("--no-decode", action="store_true", help="skip decoding every file")

    p = add("catalog", cmd_catalog, "list, show, edit, add to, remove from and check the catalog")
    actions = p.add_subparsers(dest="action", metavar="<action>", required=True)
    actions.add_parser("list", help="list the albums, oldest release first")
    a = actions.add_parser("show", help="show the tracks of an album, or every tag of one track")
    a.add_argument("album", help="text contained in the album name")
    a.add_argument("--disc", type=int)
    a.add_argument("--track", type=int)
    a = actions.add_parser("set", help="set a tag on an album's tracks (or one track)")
    a.add_argument("album")
    a.add_argument("tag", help="tag name, e.g. Genre or ItemList:Genre")
    a.add_argument("value")
    a.add_argument("--disc", type=int)
    a.add_argument("--track", type=int)
    a = actions.add_parser("unset", help="remove a tag from an album's tracks (or one track)")
    a.add_argument("album")
    a.add_argument("tag")
    a.add_argument("--disc", type=int)
    a.add_argument("--track", type=int)
    a = actions.add_parser("add", help="add an album from a spec file and its downloaded FLAC folder")
    a.add_argument("spec")
    a.add_argument("--from", dest="source", required=True, metavar="DIR", help="the album's FLAC folder")
    a.add_argument("--dry-run", action="store_true")
    a = actions.add_parser("remove", help="remove an album from the catalog (after you removed it from the Music "
                                          "app); the library is not touched")
    a.add_argument("album", help="text contained in the album name")
    a.add_argument("--dry-run", action="store_true", help="show what would be removed")
    actions.add_parser("check", help="check the catalog files for consistency")
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

    p = add("evacuate", cmd_evacuate, "move albums out of the library and remove their entries, to add them again")
    p.add_argument("--album", metavar="TEXT", help="only albums whose name contains TEXT")
    p.add_argument("--dry-run", action="store_true")

    p = add("store-entries", cmd_store_entries, "list, or delete, the Music app's entries of the store album")
    p.add_argument("--delete", action="store_true", help="delete the entries that still carry purchase data")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup(verbose=args.verbose, quiet=args.quiet)
    if not args.command:
        parser.print_help()
        return EXIT_USAGE
    home = config_mod.resolve_home(args.home)
    try:
        if args.func is cmd_init:
            return cmd_init(args, home)
        cfg = config_mod.load(home, getattr(args, "source", None) if args.func in (cmd_convert, cmd_watch) else None)
        if moved := state.migrate_backups(cfg.state):
            log.info(f"Moved {moved} old backups from state/history and state/snapshots to state/backups")
        return args.func(args, cfg)
    except (UsageError, config_mod.ConfigError) as error:
        log.error(str(error))
        return EXIT_USAGE
    except runtime.Stopped as error:
        log.info("Stopped.")
        return error.exit_code
    except KeyboardInterrupt:
        sys.stderr.write("\n")
        log.info("Interrupted.")
        return 130
    except state.LockHeld as error:
        log.error(f"{error}; run 'hist stop' to stop it")
        return EXIT_ERROR
    except proc.ToolError as error:
        log.error(f"{error}; run 'hist doctor'")
        return EXIT_ERROR
    except HistError as error:
        log.error(str(error))
        return EXIT_ERROR
