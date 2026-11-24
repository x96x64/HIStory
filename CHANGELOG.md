# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.4.1] - 2026-11-24

This release changes the name of the npm package to `@x96x64/his-story`. npm refused the name `his-story` given in
2.4.0, so 2.4.0 was published only on PyPI. The Python package, the command and its behavior are unchanged.

### Changed

- The npm package is now named `@x96x64/his-story` (a public scoped package) instead of `his-story`. npm's
  publishing policy rejected `his-story` as too similar to the existing package `history`, so the 2.4.0 release
  failed to publish to npm and no npm package of 2.4.0 exists. Install the command from npm with
  `npm install -g @x96x64/his-story`. The installed command is still `hist`, and the npm package still runs the
  bundled Python code with `python3` (3.12 or newer).
- The PyPI distribution keeps the name `his-story`; `pip install his-story` and `pipx install his-story` work as
  before and install 2.4.1.
- The README npm badge and link, the installation instructions in the README, and the release checklist in
  `docs/releasing.md` name the scoped npm package.

### Fixed

- The release workflow can publish to npm again: the `publish-npm` job of 2.4.0 stopped with `E403 Forbidden`
  because of the rejected name, which also skipped the automatic creation of the GitHub release. The 2.4.0 GitHub
  release was created by hand from the same notes.

### Migration

- No migration is needed for the catalog, the configuration or the library.
- If you tried `npm install -g his-story`, it did not install this project; use
  `npm install -g @x96x64/his-story` instead.
- Users who installed from PyPI can upgrade with `pip install --upgrade his-story` or `pipx upgrade his-story`.

## [2.4.0] - 2026-11-24

This release adds machine-readable output and batch editing for scripts and AI agents, renames the distribution to
`his-story`, and adds an npm package.

### Added

- `--json` output for `hist catalog list`, `catalog show`, `catalog edit`, `catalog check`, `dates list`,
  `dates check`, `dates set`, `dates unset`, `status`, `doctor` and `verify`. The output is one JSON document on
  standard output. With `--json` an error is printed on standard error as `{"error": {"message": ..., "code": ...}}`
  with the same exit status as in text mode. The codes are `usage`, `config`, `catalog`, `dates`, `locked`, `tool`,
  `platform` and `error`.
- `hist catalog edit [FILE|-] [--dry-run] [--retag] [--exact]`: applies a JSON array of `set` and `unset`
  operations read from FILE or standard input. Every operation is checked first, one error rejects the whole batch,
  and the result is written once with one backup. `--dry-run` prints the changes only, and `--retag` then runs
  `hist retag --apply` on the changed albums. It fails at once when standard input is a terminal.
- `hist catalog cover ALBUM IMAGE`: makes a JPEG or PNG the cover of every track of an album.
- `hist catalog export ALBUM [-o FILE]`: writes an album as a spec file that `hist catalog add` accepts. Tags that a
  spec cannot express are reported as warnings.
- `hist dates set PATH DATE [--kind album|artist]` and `hist dates unset PATH`: change `dates.json` without editing
  it by hand. Each keeps a backup.
- `--exact` for the commands that take an album name: the name must then be the full album name. Without it, text
  that matches several albums is an error that lists them.
- `hist agent-help [--json]`: prints the guide for AI agents and scripts. It works without a catalog.
- `AGENTS.md` and `CLAUDE.md` in the repository, and the same two files written into the catalog folder by
  `hist init`. Existing files are never overwritten.
- A "catalog" lock taken by every writer of `tracks.json` and `dates.json`; a second writer fails at once with the
  error code `locked`.
- After a change to the catalog, a line `hist: next: ...` on standard error names the command to run next, for
  example `hist retag`. `--quiet` hides it.
- The npm package `his-story`: a thin wrapper that runs the Python package with `python3`. Set `HIST_PYTHON` to
  choose another interpreter.
- `python -m hist`, and `hist.__version__` read from the installed `his-story` metadata. For a copy that is not
  installed it falls back to `package.json` or `pyproject.toml`.
- `scripts/check_versions.py`, which checks that the versions of `pyproject.toml`, `npm/package.json` and the
  release tag agree.
- Continuous integration on GitHub (ruff, pytest, Conventional Commits), a release workflow that publishes to PyPI
  and npm and creates the GitHub release, issue and pull request templates, and Dependabot.
- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `docs/releasing.md`, `.editorconfig`,
  `.pre-commit-config.yaml` and `commitlint.config.mjs`.
- The `dev` extra (`pip install -e '.[dev]'`), the `py.typed` marker, project URLs and more package classifiers.

### Changed

- The distribution is named `his-story` on PyPI and npm instead of `hist`. The command and the Python package are
  still `hist`. To migrate, run `pipx uninstall hist` and then `pipx install his-story`.
- `hist init` writes a complete, commented `config.toml` and asks no question.
- Errors say what to run next. `hist catalog set` and `edit` print the `hist retag` command to run.
- A missing external tool is reported with the command that installs it, for example `brew install ffmpeg`.
- Commands that need macOS (the Music app, `osascript` or `SetFile`: `status --music`, `verify --music`, `refresh`,
  `evacuate`, `store-entries`, `watch`, and `dates apply` and `dates check` when there are entries) fail at once on
  other systems with a message that says so. The catalog commands work everywhere.
- Without a catalog, every command except `init`, `agent-help` and `doctor` says to run `hist init`, or to pass
  `--home` or set `HISTORY_HOME`.
- The code is formatted and checked with ruff. This does not change behavior.
- The maintainer's workspace notes moved out of the repository; `docs/releasing.md` describes the release
  procedure.

## [2.3.0] - 2026-11-10

### Changed

- The distribution name is `hist`, the same as the command and the Python package, instead of `history-music`.
  To migrate, run `pipx uninstall history-music` and then install the new distribution, for example
  `pipx install ./HIStory` from the project folder.
- The README no longer says to clone a repository: HIStory is installed from its folder.

### Removed

- The GitHub Actions test workflow, the README badges and the repository and issue URLs in the package metadata.
  Run the tests locally with `python -m pytest`.

## [2.2.0] - 2026-11-10

### Changed

- Backups are kept in one place, `state/backups/`, with one folder per command named
  `<time>-<command>`, for example `20261110-210045-catalog-remove`. It holds every file the command changed:
  `tracks.json`, `dates.json` and removed covers for `hist catalog set`, `unset`, `add`, `remove` and `import`,
  and the files' current tags for `hist retag --apply`.
- The first `hist` command after the update moves the copies in `state/history/` and the folders in
  `state/snapshots/` into `state/backups/`, and removes the old folders when they are empty. No action is needed.

## [2.1.0] - 2026-11-10

### Changed

- The Python package is named `hist`, after the command, instead of `history_music`; `python -m hist` runs the
  command instead of `python -m history_music`. Code that imports
  `history_music` must import `hist` instead. The command and the distribution name `history-music` are unchanged.
- The package metadata, the command line help, the module docstring and `docs/commands.md` describe the project
  with one shared sentence.

## [2.0.0] - 2026-11-10

This release contains breaking changes; see the migration steps below.

### Changed

- A relative `cover` in a spec file is taken relative to the spec file's folder instead of the catalog folder.
  To migrate, make the paths in your spec files relative to the spec file's folder, or absolute.
- `hist catalog remove` no longer reports or deletes specs, and `hist init --from DIR` no longer copies a `specs/`
  folder.

### Removed

- The `specs/` folder of the catalog. `hist watch` no longer adds albums from it, and `hist init`,
  `hist doctor` and `hist catalog check` no longer look for it. A spec file is now only the input of
  `hist catalog add` and can be kept anywhere. To migrate, move the files out of `specs/` (an existing `specs/`
  folder is left in place and ignored), add each album that is not yet in the catalog with
  `hist catalog add SPEC --from DIR` once its download is complete, and run `hist catalog check`.

## [1.3.0] - 2026-11-10

### Changed

- `hist watch` and `hist catalog add` move the spec of every album that is in the catalog from `specs/` to
  `state/history/`, so that `specs/` holds only albums that are still to be added. Each move is logged as
  `Moved specs/NAME to state/history: its album is in the catalog`.

## [1.2.0] - 2026-11-10

### Added

- A GitHub Actions workflow that runs pyflakes and the tests on macOS for every push to `main` and every pull
  request, on the oldest supported Python and the newest release.
- README badges for the test status, the latest release, the supported Python versions, the platform and the
  license.
- The authors in `pyproject.toml`, and the repository and issue URLs in the package metadata. The repository name
  is written `HIStory`.

### Changed

- `hist verify` reads metadata atoms and store purchase data for up to 40 files per exiftool run instead of two
  runs per file, with the same results. On a library of 442 files `hist verify --no-decode` takes about 14 seconds
  instead of about 66.
- The README says to install from a clone of the GitHub repository instead of an unpacked ZIP file, and build output
  is no longer kept in the repository.
- The license's copyright line uses the sign © instead of "(c)".

### Removed

- Migration of state files from the tool that preceded 1.0.0 (`registered.json`, progress files stored as lists).
  A state folder that still holds these files must be converted with 1.1.0 or earlier first.

## [1.1.0] - 2026-11-10

### Added

- `hist catalog remove ALBUM [--dry-run]`: removes an album you removed from the Music app from the catalog
  folder, with its `dates.json` entries (and its artist's entry when no other album of that artist is left), its
  progress records, its spec and the covers that nothing else uses. Every changed or deleted file is kept in
  `state/history/` first. The library folder and the Music app are not touched. With `--dry-run` it shows what
  would be removed.

### Changed

- Every error that `hist` reports without a traceback now derives from one base class, `HistError`.
- `hist dates` is split into one function per action; the output is unchanged.

### Fixed

- `hist doctor` reports a `tracks.json` that is not valid JSON, as a list of problems, instead of stopping with a
  traceback.

## [1.0.0] - 2026-11-10

### Added

- `hist` command with the subcommands `init`, `doctor`, `status`, `convert`, `watch`, `stop`,
  `dates`, `verify`, `catalog`, `retag`, `refresh`, `evacuate` and `store-entries`.
- Conversion of FLAC downloads to ALAC with the catalog's tags written before conversion, and checks of decoded
  samples, duration, tags, cover and stray metadata before a FLAC file is deleted.
- `hist watch`: converts downloads as they complete, adds albums from specs, checks and dates each album you add
  to the Music app yourself, and ends when every album is converted and in the library. `hist` never adds
  albums to the Music app.
- `hist convert --dry-run`: shows how files would be paired, with durations.
- Folder and file dates from `dates.json`, with `list`, `apply`, `check` and `script`.
- Catalog editing with history copies, spec files, and import from an existing library.
- Download name aliases and renumbering for a download that is one disc of a larger set.
- Handling of one album bought in the Music app's store: purchase data removed without re-encoding.
- Safe stopping (first Ctrl-C or `hist stop` finishes the current album), locks against concurrent runs, and
  log files under `state/logs/`.

[Unreleased]: https://github.com/x96x64/HIStory/compare/v2.4.1...HEAD
[2.4.1]: https://github.com/x96x64/HIStory/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/x96x64/HIStory/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/x96x64/HIStory/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/x96x64/HIStory/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/x96x64/HIStory/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/x96x64/HIStory/compare/v1.3.0...v2.0.0
[1.3.0]: https://github.com/x96x64/HIStory/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/x96x64/HIStory/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/x96x64/HIStory/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/x96x64/HIStory/releases/tag/v1.0.0
