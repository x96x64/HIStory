# HIStory

HIStory (`hist`) rebuilds an Apple Music library on macOS from FLAC downloads, so that every track ends up as an Apple Lossless (ALAC) file whose tags and cover art are exactly the ones recorded in a catalog you control.

[![CI](https://github.com/x96x64/HIStory/actions/workflows/ci.yml/badge.svg)](https://github.com/x96x64/HIStory/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/his-story?label=PyPI)](https://pypi.org/project/his-story/)
[![npm](https://img.shields.io/npm/v/@x96x64/his-story?label=npm&cacheSeconds=21600)](https://www.npmjs.com/package/@x96x64/his-story)
[![Python versions](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)](https://pypi.org/project/his-story/)
[![License](https://img.shields.io/github/license/x96x64/HIStory)](https://github.com/x96x64/HIStory/blob/main/LICENSE)

## Overview

`hist` keeps a catalog of the exact tags of every track you want in your library. The catalog is a plain JSON file (`tracks.json`) plus cover images, so it can be read, reviewed, backed up and edited like any other text. When the FLAC files of an album finish downloading, `hist` writes the catalog's tags and cover into them, converts them to ALAC with ffmpeg, checks every result against the catalog, and only then deletes the FLAC files.

You add the converted albums to the Music app yourself, one album at a time. `hist` never adds anything to the Music app. While `hist watch` runs, it notices each album that appears in the library folder, compares its files with the catalog, and sets the creation and modification dates of the artist and album folders from `dates.json`, so that the Music app and your devices show the albums in the order you chose.

The conversion is lossless and verified. Each M4A must decode to exactly the same samples as its FLAC source, have the same duration (within 0.5 seconds), carry exactly the catalog's tags and cover, and contain no other metadata. A file that fails any check is not accepted, and its FLAC source is kept.

## Features

- A catalog of exact tags in `tracks.json`, edited with `hist catalog` commands: `list`, `show`, `set`, `unset`, `edit`, `cover`, `export`, `add`, `remove`, `check` and `import`.
- Lossless conversion from FLAC to ALAC with ffmpeg, with a sample-by-sample comparison, a duration check and a check that no stray metadata is present.
- Album folder and file dates set from `dates.json`, with `hist dates` commands to list, set, unset, apply and check them.
- `hist verify` checks the library (and optionally the Music app) against the catalog, including track counts, store purchase data and release order.
- `hist watch` converts downloads as they complete, checks the albums you add, and ends by itself when every album is converted and in the library. It can be stopped safely at any time with Ctrl-C or `hist stop`.
- `hist retag` writes changed catalog tags back into existing M4A files, saving the previous tags first.
- Machine-readable output with `--json` on the read commands, a batch editor with `--dry-run`, and a built-in guide for AI agents (`hist agent-help`).
- Safe by construction: every change to the catalog keeps a backup, and writers take a lock so that two processes never write the catalog at once.
- No third-party Python dependencies: the tool uses only the Python standard library and calls the external programs listed below.

## Requirements

- Python 3.12 or newer.
- For work on a library: macOS with the Music app, because `hist` talks to it with `osascript` and sets folder dates with `SetFile`.
- `ffmpeg` (with the ALAC encoder) and `ffprobe`, `flac` and `metaflac`, and `exiftool`. On macOS, `brew install ffmpeg flac exiftool` installs them.
- The Xcode command line tools for `SetFile` (`xcode-select --install`), needed by `hist dates apply` and `hist dates check`.
- The catalog commands (`hist catalog ...`, `hist dates list`, `hist dates set`, `hist doctor`, `hist agent-help`) work on any operating system. Commands that need the Music app or `SetFile` fail at once, with a clear message, on other systems.

Run `hist doctor` at any time to see which of these are present on your machine.

## Installation

Install with `pipx`, which keeps the tool and its environment separate from other Python projects (recommended):

```sh
pipx install his-story
```

Or with `pip`, into the Python environment of your choice:

```sh
pip install his-story
```

Or with npm, from the package `@x96x64/his-story`. The npm package is a thin wrapper that runs the bundled Python code with `python3` (3.12 or newer), so Python must still be installed:

```sh
npm install -g @x96x64/his-story
```

To work on the code, install from a clone of the repository in editable mode:

```sh
git clone https://github.com/x96x64/HIStory.git
cd HIStory
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/hist --version
```

All four ways install the same command, `hist`. Install the external tools from the Requirements section separately.

## Quick Start

Create the catalog folder, check that your machine is ready, and add a first album. A spec file describes the tags of an album (see [docs/catalog-format.md](https://github.com/x96x64/HIStory/blob/main/docs/catalog-format.md)); the folder holds its downloaded FLAC files.

```sh
hist init                                   # create an empty catalog (or: hist init --from DIR)
hist doctor                                 # check the tools, the configuration and the catalog
hist catalog add album.json --from ~/Downloads/Album   # add an album from a spec and its FLAC folder
hist convert --dry-run                      # show how the files would be paired with the catalog
hist convert                                # convert every complete download
hist status                                 # see how far each album has come
```

Then add the converted albums to the Music app, and let `hist` set their dates and check them:

```sh
hist dates apply                            # set the folder and file dates from dates.json
hist verify                                 # check the library's files against the catalog
hist verify --music                         # also check the Music app's entries
```

Instead of running `convert` and `dates apply` by hand, you can leave `hist watch` running. It converts each download as soon as it is complete, dates each album when you add it to the Music app, and exits by itself when everything is done.

## Usage Overview

Every command is described, with all of its options, in [docs/commands.md](https://github.com/x96x64/HIStory/blob/main/docs/commands.md). The commands fall into these groups.

| Group | Commands | Purpose |
| --- | --- | --- |
| Setup | `init`, `doctor`, `agent-help` | Create the catalog folder, check the machine, print the guide for agents |
| Catalog | `catalog list`, `show`, `set`, `unset`, `edit`, `cover`, `export`, `add`, `remove`, `check`, `import` | Read and change the exact tags |
| Conversion | `convert`, `watch`, `stop`, `status` | Turn downloads into verified ALAC files and follow progress |
| Dates | `dates list`, `apply`, `check`, `script`, `set`, `unset` | Manage the folder and file dates |
| Checking | `verify`, `retag`, `refresh` | Compare files with the catalog and repair differences |
| Music app | `evacuate`, `store-entries` | Remove albums from the Music app so they can be added again |

Global options go before the command: `--home DIR` selects the catalog folder, `-q` prints warnings and errors only, `-v` prints more detail, and `--version` prints the version. Run `hist <command> --help` for the options of one command.

## The Catalog

The catalog is a folder (see Configuration for where it is) that holds everything `hist` needs to know about your library: `config.toml` for settings, `tracks.json` for the exact tags, `covers/` for cover images named by their SHA-256 hash, and `dates.json` for folder dates. A `state/` folder holds progress records, logs, locks and backups; it is created by `hist` and is not part of the catalog. The exact file formats are described in [docs/catalog-format.md](https://github.com/x96x64/HIStory/blob/main/docs/catalog-format.md).

Changes are made with `hist catalog` commands rather than by hand. Each command that changes `tracks.json` or `dates.json` first checks the change, then writes the file once, and keeps the previous files in a new folder `state/backups/<time>-<command>/`. A rejected change leaves the catalog untouched.

Writers take an exclusive lock named "catalog", so a second writer fails at once with the error code `locked` instead of corrupting the files. `hist catalog check` verifies that the catalog is consistent, and `hist doctor` reports whether `watch` or `convert` is currently running.

`hist catalog remove` removes an album from the catalog only. It never touches the library folder or the Music app, and it keeps every changed file in one backup folder first.

## Using hist with AI Agents

`hist` is designed to be driven by scripts and AI agents as well as by people. The read commands (`catalog list`, `show`, `check`, `dates list`, `dates check`, `status`, `doctor` and `verify`) accept `--json` and print one JSON document on standard output. With `--json`, an error is printed on standard error as `{"error": {"message": ..., "code": ...}}`, and the exit status is the same as in text mode.

Tags are changed with `hist catalog edit`, which reads a JSON array of `set` and `unset` operations from a file or from standard input. Every operation is checked before anything is written, and one invalid operation rejects the whole batch. Always preview first:

```sh
echo '[{"op": "set", "album": "Album Name", "tag": "Genre", "value": "Soul"}]' | hist catalog edit --dry-run
echo '[{"op": "set", "album": "Album Name", "tag": "Genre", "value": "Soul"}]' | hist catalog edit --json
```

The guide for agents ships inside the tool: `hist agent-help` prints it as Markdown, and `hist agent-help --json` prints it as JSON. It works without a catalog. The same text is the repository's [AGENTS.md](https://github.com/x96x64/HIStory/blob/main/AGENTS.md), and `hist init` writes it into the catalog folder as `AGENTS.md` and `CLAUDE.md`.

## Configuration

The catalog folder is chosen in this order: the `--home DIR` option, the `HISTORY_HOME` environment variable, and finally `~/Library/Application Support/HIStory`. `hist init` creates the folder and a fully commented `config.toml`. Paths in `config.toml` may start with `~`; a relative path is taken relative to the catalog folder.

| Key | Meaning |
| --- | --- |
| `[paths] downloads` | List of folders that receive downloaded albums, one sub-folder per album |
| `[paths] library` | The Music app's media folder (default `~/Music/Music/Media.localized/Music`) |
| `[paths] auto_add` | The "Automatically Add to Music" folder of the Music app |
| `[paths] evacuation` | Where `hist evacuate` moves album folders out of the library |
| `[convert] min_free_gb` | An album is not converted unless this much space stays free (default 10) |
| `[store] album`, `file` | Optional: one album bought in the Music app's store and how to find its file |
| `[match.aliases]` | Optional: download album names that differ from the catalog's |
| `[match.renumber."Album"]` | Optional: `disc` and `offset` for a download that is one disc of a larger set |

## Troubleshooting

Start with `hist doctor`, which checks Python, the external tools, the configuration, the catalog, the dates file, the folders and the free disk space, and names the command that installs anything missing. For common errors, the exact messages `hist` prints and how to fix them, see [docs/troubleshooting.md](https://github.com/x96x64/HIStory/blob/main/docs/troubleshooting.md).

When a command fails, the message says what to run next. Run it again with `-v` for more detail, and read the log of `hist watch` in `state/logs/watch.log` inside the catalog folder. If the problem persists, open an issue on GitHub and include the output of `hist --version` and `hist doctor`.

## Development and Contributing

Contributions are welcome. [CONTRIBUTING.md](https://github.com/x96x64/HIStory/blob/main/CONTRIBUTING.md) explains how to set up a development environment, run the tests and submit a pull request, and [CODE_OF_CONDUCT.md](https://github.com/x96x64/HIStory/blob/main/CODE_OF_CONDUCT.md) describes the behavior expected in the project. The repository's [AGENTS.md](https://github.com/x96x64/HIStory/blob/main/AGENTS.md) documents the conventions that AI coding agents and people follow when changing the code.

The tool itself needs only the Python standard library; the tests use pytest. After `pip install -e '.[dev]'`, run `python -m pytest -q`, `ruff check .` and `ruff format --check .`. The tests never touch a real Music app or catalog, and tests that need ffmpeg, flac or exiftool skip themselves when those are missing. See CONTRIBUTING.md for the exact commands used by CI. The release process is described in [docs/releasing.md](https://github.com/x96x64/HIStory/blob/main/docs/releasing.md).

## Versioning and Changelog

The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The current version is 2.5.0; `hist --version` prints the installed one. The same version is published on PyPI as `his-story` and on npm as `@x96x64/his-story`.

Every notable change is recorded in [CHANGELOG.md](CHANGELOG.md), in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Read it before upgrading, because changes to the catalog format or to command behavior are listed there.

## Security

Please do not report security problems in a public issue. [SECURITY.md](SECURITY.md) describes which versions are supported and how to report a vulnerability privately.

`hist` runs external programs (ffmpeg, flac, exiftool, osascript, SetFile) without a shell and makes no network connections and needs no credentials. It writes only to the catalog folder, the download folders and, when you ask for it, the library folder and the Music app.

## License

HIStory is released under the MIT License; the full text is in the [LICENSE](https://github.com/x96x64/HIStory/blob/main/LICENSE) file. The license applies to the code and the documentation in this repository, and to the packages published on PyPI and npm.

Copyright is held by the HIStory contributors. Contributions are accepted under the same license.
