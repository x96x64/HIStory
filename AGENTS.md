# AGENTS.md

## Project Overview

`hist` is a command-line tool that rebuilds an Apple Music library on macOS from FLAC downloads with exact, verified tags. A catalog (`tracks.json`, `covers/`, `dates.json`) holds the tags every track must have. The package is `hist/` and the command is `hist` (`hist.cli:main`). The documentation is in `README.md` and `docs/`.

## Setup

```sh
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pre-commit install  # optional: pip install pre-commit
```

## Build and Test Commands

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q tests/test_agent.py
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/ruff check --fix . && .venv/bin/ruff format .
.venv/bin/hist --help
.venv/bin/python -m build  # needs: pip install build
```

## Code Style

- Python 3.12 or newer and the standard library only; do not add dependencies.
- Use type hints on function signatures, short docstrings, and lines of at most 120 characters; `ruff check` and `ruff format --check` must pass.
- Commands are `argparse` sub-commands in `hist/cli.py`; keep the logic in the other modules and keep `cli.py` thin.
- Write help text and documentation in clear, formal English with ASCII quotes.

## Testing Instructions

- Tests are in `tests/` and call `hist.cli.main([...])` in process.
- `tests/conftest.py` points `HOME` and `HISTORY_HOME` into a temporary folder and makes `MusicApp.osa` fail, so a test can never touch the real Music app or catalog.
- Add or update tests for every change, and run the whole suite before you commit. Tests that need ffmpeg, flac, exiftool or SetFile skip themselves when the tools are missing.

## Using hist to Edit Metadata

Never edit `tracks.json` or `dates.json` by hand; use the commands below.

hist keeps the exact tags of every track in a catalog (tracks.json, covers/, dates.json). Read and change the catalog only through hist; do not edit its JSON files by hand.

- No command asks a question. 'catalog edit' reads standard input when FILE is '-' or omitted, and fails at once when that is a terminal.
- Name an album with text from its name; if the text matches several albums the command fails and lists them. Use --exact with the full name (from 'hist catalog list --json') to be sure.
- Every change to the catalog keeps the previous files in <home>/state/backups/. One writer runs at a time; a second one fails at once with code 'locked'.
- Changing the catalog does not change the files in the library. Run 'hist retag' afterwards.

1. Inspect

```sh
hist catalog list --json
hist catalog show "Album Name" --json
hist status --json
hist dates list --json
hist catalog check --json
hist doctor --json
```

2. Preview

```sh
hist catalog edit ops.json --dry-run --json
```

3. Apply

```sh
hist catalog edit ops.json
```

4. Propagate

```sh
hist retag "<library>/Artist/Album Name" --apply
hist dates apply --only "Album Name"
```

5. Verify

```sh
hist catalog check --json
```

Commands:

- `hist catalog list [--json]`: list the albums, oldest release first
- `hist catalog show ALBUM [--disc N] [--track N] [--exact] [--json]`: show the tracks of an album with every tag
- `hist catalog edit [FILE|-] [--dry-run] [--retag] [--exact] [--json]`: apply a JSON array of set and unset operations in one write, with one backup
- `hist catalog set ALBUM TAG VALUE [--disc N] [--track N] [--exact]`: set one tag on an album or one track
- `hist catalog unset ALBUM TAG [--disc N] [--track N] [--exact]`: remove one tag
- `hist catalog cover ALBUM IMAGE [--exact]`: make a JPEG or PNG the cover of an album
- `hist catalog export ALBUM [-o FILE] [--exact]`: write the album as a spec file that 'catalog add' accepts
- `hist catalog check [--json]`: check the catalog for problems; exit 1 if any
- `hist dates list [--json]`: list the entries of dates.json
- `hist dates set PATH DATE [--kind album|artist] [--json]`: set an entry (PATH is Artist or Artist/Album, DATE is YYYY-MM-DD)
- `hist dates unset PATH [--json]`: remove the entries of PATH
- `hist dates check [--json]`: compare the library's dates with dates.json
- `hist retag PATH... [--apply]`: write the catalog's tags into the M4A files under PATH
- `hist status [--json]`: show how far each album has come
- `hist doctor [--json]`: check the tools, the configuration and the catalog

`catalog edit` takes a JSON array of operations, from FILE or from standard input ('-'). Keys of an operation:

- `op`: "set" or "unset" (required)
- `album`: text contained in the album name (required)
- `tag`: tag name, with or without its group: Genre or ItemList:Genre (required)
- `value`: the new value, a non-empty string ('set' only, required there)
- `disc`: integer; limits the operation to one disc (optional)
- `track`: integer; limits the operation to one track number (optional)
- `exact`: true: album is the album's exact name (optional)

- Without disc and track an operation covers the whole album.
- Every operation is checked before anything is written; one error rejects the whole batch.
- Title, Album, AlbumArtist, Artist, TrackNumber and DiskNumber cannot be removed; Comment and Encoder are never stored.

Example `ops.json`:

```json
[
 {
  "op": "set",
  "album": "Album Name",
  "disc": 1,
  "track": 3,
  "tag": "Title",
  "value": "New Title"
 },
 {
  "op": "set",
  "album": "Album Name",
  "tag": "Genre",
  "value": "Soul"
 },
 {
  "op": "unset",
  "album": "Album Name",
  "tag": "Composer"
 }
]
```

Exit codes:

- `0`: success
- `1`: an error, or a check found problems
- `2`: a usage or configuration error
- `130`: interrupted (Ctrl-C)
- `143`: stopped by SIGTERM

With --json an error is printed on standard error as {"error": {"message": ..., "code": ...}}. Codes: `usage`, `config`, `catalog`, `dates`, `locked`, `tool`, `error`.

## Commit and Pull Request Guidelines

- Use Conventional Commits 1.0: `type(scope): subject`.
- Write the subject in the imperative mood, in lowercase, without a final period, in at most 72 characters.
- Wrap the body at 72 characters when the change is not trivial, and explain why.
- Keep each commit to one logical change, and update `docs/commands.md` and `CHANGELOG.md` (section Unreleased) with every change of behavior.

## Security Considerations

- Every command that changes the catalog keeps the previous files in `state/backups/` first.
- `hist` makes no network connections and needs no credentials; do not commit secrets or a real catalog.
- Commands that change the Music app or the library folder are marked in `docs/commands.md`; tests never run them against a real library.
