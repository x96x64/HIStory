# hist(1)

## NAME

hist - rebuild an Apple Music library on macOS from FLAC downloads with exact, verified tags

## SYNOPSIS

```
hist [--home DIR] [-q | --quiet] [-v | --verbose] <command> [<args>]
hist --version
hist [<command>] --help
```

## DESCRIPTION

`hist` converts downloaded FLAC albums to Apple Lossless files whose tags equal a catalog. You add the converted
albums to the Music app yourself, one at a time; `hist` checks each album you add and sets the dates of its
folders and files. `hist` never adds anything to the Music app.

Commands that change the Music app or its library folder on request are marked **writes to Music** below. All other
commands write only to the catalog folder and the download folders.

## GLOBAL OPTIONS

`--home DIR`
: The catalog folder. Default: `$HISTORY_HOME`, else `~/Library/Application Support/HIStory`.
Give it before the command name.

`-q`, `--quiet`
: Print warnings and errors only. Results that a command exists to show (listings, checks, `hist stop`) are
still printed on standard output; progress lines are not.

`-v`, `--verbose`
: Print more detail.

`--version`
: Print the version and exit.

## COMMANDS

### hist init [--from DIR] [--force]

Create the catalog folder with a complete, commented `config.toml` (no questions are asked), `AGENTS.md` and
`CLAUDE.md` (existing files are never overwritten), an empty `tracks.json` and `dates.json`. With `--from`,
copy an existing catalog (`config.toml`, `tracks.json`, `covers/`, `dates.json`) into it and check it.
A catalog that already holds tracks is replaced only with `--force`.

### hist agent-help [--json]

Print the guide for AI agents and scripts: the same text as `AGENTS.md` in the catalog folder, as Markdown or
(with `--json`) as JSON. It works without a catalog.

### hist doctor [--json]

Check Python, the external tools, the configuration, the catalog, the dates file, the folders, free disk space,
and whether `watch` or `convert` is running. With automatic download folders it lists the ones it found; a
listed download folder that does not exist is reported as information, not as a warning. Exits 1 if something required is missing. A missing tool is named
with the command that installs it, for example `brew install ffmpeg`. With `--json`, print
`{"ok", "checks", "info"}`.

### hist status [--music] [--json]

Print one line per album, oldest release first: in the library, converted and ready to add, ready to convert, or
what it is waiting for. With `--music`, also count each album's tracks in the Music app (macOS only). With
`--json`, print `{"total", "albums": [...]}`.

### hist convert [--only TEXT] [--keep-flac] [--source DIR]... [--dry-run]

Convert every complete download once, oldest release first. For each track: write the catalog's tags and cover
into the FLAC file, convert it to ALAC, check that the M4A decodes to the same samples, has the same duration
(within 0.5 s), carries exactly the catalog's tags and no other metadata, rename it to `NN Title.m4a`
(`D-NN Title.m4a` for several discs), and delete the FLAC file. A download is complete when the folder holds as
many FLAC files as the album has tracks, no unfinished download files, nothing changed in the last 10 seconds,
and every file decodes cleanly.

`--only TEXT`
: Only albums whose name contains TEXT.

`--keep-flac`
: Keep the FLAC files after the checks (needs about twice the space).

`--source DIR`
: Use this download folder instead of the configured ones (repeatable).

`--dry-run`
: Show how the files of each complete download would be paired with the catalog's tracks, with durations.
Nothing is written.

An album is skipped while free space would fall below `min_free_gb`. Files left by an interrupted run are
replaced; a FLAC file is deleted only after its M4A passed every check.

### hist watch [--only TEXT] [--keep-flac] [--source DIR]... [--interval SECONDS] [--log FILE] [--convert-only]

Look at the download folders and the library every 10 seconds (see `--interval`).

Downloads: convert every complete download of an album in the catalog as `hist convert` does. Add a new album
to the catalog first with `hist catalog add`.

Library: you add the converted albums to the Music app yourself (drag the album folder into the Music window, or
File > Add to Library). When an album appears in the library folder and its files stop changing, `hist watch`
compares its files with the catalog, sets the dates of its artist folder and album folder from `dates.json`, and
records it as added. An album whose files differ from the catalog is reported and not dated. An album that leaves
the library is forgotten and checked again when it is added again. The log names the next album to add, in release
order, and says whether it is converted yet.

`hist watch` ends by itself, with exit status 0, when every album of the catalog is converted and in the library.
Lines are also written to `state/logs/watch.log`.

`--convert-only`
: Do not watch the library; end when every album is converted.

`--interval SECONDS`
: Time between looks at the folders. Default: 10.

`--log FILE`
: Log file. Default: `<home>/state/logs/watch.log`.

### hist stop

Send SIGTERM to a running `watch` or `convert`. Each finishes the album it is working on, then exits. It prints
"Nothing is running" when no process holds the lock; a process id left in `convert.lock` after a crash is
ignored.

### hist dates list | apply | check | script | set | unset [--only TEXT] [--dry-run] [--json]

Folder and file dates in the library, from `dates.json`.

`list`
: Every entry, and whether its folder is in the library.

`apply`
: **Writes to the library folder.** Set the creation and modification dates of every entry whose folder exists.
With `--dry-run`, show what would be set.

`check`
: Check the dates; exits 1 on any mismatch.

`script`
: Print the same work as shell commands, without running them.

`set PATH DATE [--kind album|artist]`
: Add or change the entry for PATH (`Artist` or `Artist/Album`) in `dates.json`; DATE is `YYYY-MM-DD`. The kind
is inferred from PATH. The previous file is kept in `state/backups/`. Nothing is applied to the library.

`unset PATH`
: Remove the entries of PATH. Exits 1 when there is none.

`--json` works with `list`, `check`, `set` and `unset`. `apply` and `check` need macOS (`SetFile`) when there are
entries.

`--only TEXT` selects entries whose path contains TEXT; the artist entry of each selected album comes along.

### hist verify [--music] [--downloads] [--path DIR]... [--allow-missing] [--no-decode]

Check the library's M4A files against the catalog: every track present once, tags and cover equal, no Comment or
Encoder tag, a disc number on every track, no unexpected metadata, no store purchase data, no download id in a
file name, every file decodes cleanly, and every album complete. Exits 1 on any problem.

`--music`
: Also check the Music app: no store versions, the right track count per album, and albums added in release order.

`--downloads`
: Also check converted files still in the download folders.

`--path DIR`
: Check this folder instead of the library (repeatable).

`--allow-missing`
: Do not fail because tracks or albums are missing.

`--no-decode`
: Skip decoding every file.

### hist catalog \<action\>

Actions: `list`, `show`, `set`, `unset`, `edit`, `cover`, `export`, `add`, `remove`, `undo`, `check`, `import`.

Every action that takes ALBUM accepts `--exact`: ALBUM must then be the full album name. Without it, ALBUM is text
contained in the name; text that matches several albums is an error that lists them. Every writer takes the
"catalog" lock, so a second writer fails at once (error code `locked`).

`list [--json]`
: The albums, oldest release first, with track counts.

`show ALBUM [--disc N] [--track N] [--exact] [--json]`
: The tracks of an album, or every tag of one track.

`edit [FILE|-] [--dry-run] [--retag] [--exact] [--json]`
: Apply a JSON array of `set` and `unset` operations (keys `op`, `album`, `disc`, `track`, `tag`, `value`,
`exact`) read from FILE or standard input. Every operation is checked first; one error rejects the batch. The
result is written once, with one backup. `--dry-run` prints the changes only. `--retag` then runs `hist retag
--apply` on the changed albums; it cannot be combined with `--json` or `--dry-run`. With `--json` the report includes `"next"`, the commands to run afterwards.
It fails at once if standard input is a terminal.

`cover ALBUM IMAGE [--exact]`
: Make a JPEG or PNG the cover of every track of an album.

`export ALBUM [-o FILE | --output FILE] [--exact]`
: Write the album as a spec file that `catalog add` accepts (covers are written next to FILE). Tags a spec cannot
express are reported as warnings.

`set ALBUM TAG VALUE [--disc N] [--track N] [--exact]`
: Set a tag on every track of an album, or on one track. TAG may omit the group: `Genre` means `ItemList:Genre`.
Known tag names are matched ignoring case (`genre` is `ItemList:Genre`). The value is checked exactly like an
operation of `edit` (for example TrackNumber must look like `3 of 12`, and the result must not give two tracks the
same album, disc and track). The previous `tracks.json` is kept in `state/backups/`.

`unset ALBUM TAG [--disc N] [--track N] [--exact]`
: Remove a tag. Title, Album, AlbumArtist, Artist, TrackNumber and DiskNumber cannot be removed.

`add SPEC --from DIR [--dry-run]`
: Add an album from a spec file and the folder of its downloaded FLAC files. The spec file can be kept anywhere;
see docs/catalog-format.md. The spec is rejected when two tracks have the same disc and track number, a disc is
higher than `discs`, `release` is not a real date written `YYYY-MM-DD`, or the catalog already has an album of the
same name by a different album artist (run `remove` first to replace it). An album of the same name and artist is
replaced.

`undo [--dry-run] [--json]`
: Restore `tracks.json` and `dates.json` from the newest folder of `state/backups/` that holds one of them (a
backup of `retag` is not used), and put back the covers of that folder that are missing from `covers/`. The files
it replaces are kept first in a new backup folder `<time>-catalog-undo`, so a second `undo` redoes the change. It
holds the catalog lock. A backup whose `tracks.json` or `dates.json` is malformed is refused, and nothing is
changed. When a command created `tracks.json` or `dates.json`, its backup folder holds an empty marker
`<name>.absent`; `undo` then removes the file (listed as `removed` in the report, next to `restored`), and the
removed file is kept in the undo backup, so a second `undo` brings it back. `state/added.json` and
`state/converted.json` are not restored. The library files keep their
tags until `hist retag`. With `--dry-run`, show what would be restored.

`remove ALBUM [--dry-run] [--exact]`
: Remove an album from the catalog folder after you have removed it from the Music app: its tracks, its
`dates.json` entries (and its artist's entry when no other album of that artist is left), its records in
`state/added.json` and `state/converted.json`, and covers that nothing else uses. Every changed or
deleted file is kept in one folder of `state/backups/` first. The library folder and the Music app are not touched. With
`--dry-run`, show what would be removed.

`check [--json]`
: Check the catalog files for consistency; exits 1 on any problem. A `tracks.json` that is not valid JSON or has
malformed records is reported as a problem, not as a crash.

`import FOLDER`
: Start an empty catalog from the tags of the M4A files under an existing library folder, dropping Comment and
Encoder. It fails when the catalog already holds tracks ("the catalog in HOME already holds tracks") or when the
folder holds no M4A files.

### hist retag PATH... [--apply] [--fields LIST] [--prune] [--list-unmatched]

Match the M4A files under each PATH to the catalog and show the tags that differ. With `--apply`, save the
current tags to `state/backups/`, then write the catalog's tags. Writing changes the files' dates, so run
`hist dates apply` afterwards for albums in the library, and `hist refresh` for albums in the Music app.

### hist refresh ALBUM [--exact]

**Writes to Music.** Make the Music app re-read the files of an album (tags, cover and file names). No entry is
added or removed.

### hist evacuate [--album TEXT] [--dry-run]

**Writes to Music.** Move the library folders of the catalog's albums to the `evacuation` folder, then remove
their entries from the Music app. Nothing is deleted from disk. Add them again from that folder in the Music app,
one at a time, while `hist watch` runs.

### hist store-entries [--delete]

List the Music app's entries of the album named in `[store]`, and say which still carry store purchase data.
With `--delete` (**writes to Music**), delete those entries, but only if the cleaned copy made by
`hist convert` equals the catalog and has the same audio as every entry to be deleted.

## CATALOG EDIT OPERATIONS

`hist catalog edit` reads a JSON array of objects. Unknown keys are rejected.

| Key | Type | Meaning |
| --- | --- | --- |
| `op` | string, required | `"set"` or `"unset"` |
| `album` | string, required | Text contained in the album name (the exact name with `"exact": true`) |
| `tag` | string, required | Tag name, with or without its group: `Genre` or `ItemList:Genre` |
| `value` | string | The new value; required and non-empty for `set`; not allowed for `unset` |
| `disc` | integer, optional | Limit the operation to one disc |
| `track` | integer, optional | Limit the operation to one track number |
| `exact` | boolean, optional | `album` is the exact album name |

Without `disc` and `track`, an operation covers the whole album. Title, Album, AlbumArtist, Artist, TrackNumber
and DiskNumber cannot be removed; Comment and Encoder are never stored.

```json
[
 {"op": "set", "album": "Album Name", "disc": 1, "track": 3, "tag": "Title", "value": "New Title"},
 {"op": "set", "album": "Album Name", "tag": "Genre", "value": "Soul"},
 {"op": "unset", "album": "Album Name", "tag": "Composer"}
]
```

## JSON OUTPUT

With `--json`, `catalog list`, `show`, `edit`, `undo`, `check`, `dates list`, `check`, `set`, `unset`, `status`, `doctor`
and `verify` print one JSON document on standard output. An error is printed on standard error as
`{"error": {"message": ..., "code": ...}}`, with the same exit status as in text mode. A command-line usage error is reported the same way (code `usage`,
exit status 2) when `--json` is among the arguments, also when it is abbreviated (for example `--js`), but not
after a literal `--`. File and input errors (a missing file, a file that is not valid
JSON or UTF-8) have the code `error`. Codes: `usage`, `config`,
`catalog`, `dates`, `locked`, `tool`, `platform`, `error`. `agent-help --json` prints the guide as JSON.

## PLATFORMS

Commands that use the Music app, `osascript` or `SetFile` (`status --music`, `verify --music`, `refresh`,
`evacuate`, `store-entries`, `watch`, `dates apply` and `dates check`) fail at once on other systems with a message
saying so. The catalog commands work everywhere. Without a catalog, every command except `init`, `agent-help`
and `doctor` says to run `hist init` (or to pass `--home` or set `HISTORY_HOME`).

## EXIT STATUS

| Status | Meaning |
| --- | --- |
| 0 | Success, or everything is done |
| 1 | An error, or a check failed |
| 2 | A usage or configuration error |
| 130 | Stopped by Ctrl-C |
| 143 | Stopped by SIGTERM (`hist stop`) |

## STOPPING

The first Ctrl-C, or `hist stop`, lets `watch` and `convert` finish the album they are working on; while they
are only waiting, they stop at once. A second Ctrl-C or SIGTERM stops at once; files left by an interrupted conversion are
replaced by the next run.

## ENVIRONMENT

`HISTORY_HOME`
: The catalog folder, unless `--home` is given.

## FILES

`<home>` is the catalog folder. `state/converted.json` and `state/added.json` map album names to records with a
`time`.

```
<home>/config.toml        settings
<home>/tracks.json        the catalog's tags
<home>/covers/            cover images, named by SHA-256
<home>/dates.json         folder and file dates
<home>/state/             converted.json, added.json, backups/, staging/, logs/, *.lock
```

## EXAMPLES

Convert while downloading, and date each album as you add it to the Music app:

```sh
hist watch
```

Fix a genre and bring an album in the library in line:

```sh
hist catalog set "Album Name" Genre Soul
hist retag "<library>/Artist/Album Name" --apply
hist refresh "Album Name"
hist dates apply --only "Album Name"
```

## SEE ALSO

README.md, docs/catalog-format.md, docs/troubleshooting.md, AGENTS.md
