# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `hist stop` no longer signals an unrelated process after a crash: a process id in `convert.lock` is trusted only
  while the lock is really held.
- `hist catalog undo` after a command that created `tracks.json` or `dates.json` now removes that file instead of
  restoring an older, unrelated backup. The report lists these files under `removed`, and a second undo brings
  them back.
- Files written by `hist` (`tracks.json`, `dates.json` and others) keep the permissions of the file they replace,
  and a new file gets the usual permissions of the umask instead of `0600`.

## [2.5.1] - 2026-11-24

### Changed

- When `[paths] downloads` is empty or missing, `hist` detects the download folders of common music services
  instead of scanning nothing: `~/Music/mora`, `~/Music/OTOTOY`, `~/Music/Qobuz`, `~/Music/Qobuz Downloads`,
  `~/Music/e-onkyo music`, `~/Music/HDtracks`, `~/Music/7digital`, `~/Music/Bandcamp`, `~/Music/Downloads`,
  `~/Downloads/Music`, `~/Downloads/mora`, `~/Downloads/OTOTOY`, `~/Downloads/Qobuz` and `~/Downloads/Bandcamp`.
  Every one of them that exists is scanned, and one that appears later is picked up by the next scan. The whole
  `~/Downloads` folder is never scanned. `hist init` writes `downloads = []` with a comment that explains this. To
  use the detection, empty the `downloads` list in `config.toml`; a non-empty list keeps working as before.
- `hist doctor` no longer warns about a listed download folder that does not exist yet, and no longer fails when no
  download folder is set. It names the folders it found, and lists absent ones under `info`. `hist watch` names only
  the download folders that exist when it starts.
- The default `evacuation` folder, where `hist evacuate` moves album folders out of the library, is
  `~/Desktop/HIStory Evacuated` instead of `~/Music/HIStory Evacuated`. A `config.toml` that sets `evacuation` is
  not affected. To keep the old folder, add `evacuation = "~/Music/HIStory Evacuated"` under `[paths]`.

## [2.5.0] - 2026-11-24

### Added

- `hist catalog undo [--dry-run] [--json]` restores `tracks.json` and `dates.json` (and covers that are missing)
  from the newest backup in `state/backups/`. It first keeps the files it replaces in a new backup, so a second
  `undo` redoes the change. It holds the catalog lock and refuses a backup whose `tracks.json` or `dates.json` is
  malformed, so that it never restores a file that later commands would reject. It is listed in `docs/commands.md`
  and in the agent guide.

### Changed

- With `-q`, the listing of `hist dates list`, the result of `hist dates check` and the messages of `hist stop` are
  still printed on standard output.
- Starting `hist` is faster because the package version is read only when it is needed (`hist --version`).
- `config.toml` is validated strictly: an unknown section or key, a value of the wrong type (such as a text for
  `downloads` or `min_free_gb`) and a negative `min_free_gb` are configuration errors (exit status 2, code
  `config`). Earlier versions iterated a text `downloads` character by character. To migrate, run `hist doctor`
  after the upgrade and remove or correct each key it names in `config.toml`.
- The `publish-npm` job of the release workflow waits for `publish-pypi`, so that npm never receives a version that
  failed on PyPI.
- The conversion decodes each new M4A file once instead of twice; the second check ran after a rename that does not
  change the content.
- `hist catalog edit` finds the tracks of an operation with an index, which is faster for large albums.

### Fixed

- `hist convert` and `hist watch` resume an album whose conversion was interrupted. Before, the tracks that were
  already converted (their FLAC files deleted) were not counted, so the album was reported as "still downloading"
  and never finished. An album also resumes when the run stopped after a FLAC file had been tagged with the
  catalog's names but before it was deleted: every file of the chosen folder is now compared as the catalog's album
  and artist, and a leftover M4A file is matched with the catalog track its FLAC pairs with, not only with the FLAC's
  own tags.
- File and input errors (a missing cover or edit file, an unwritable export path, a file that is not valid JSON or
  UTF-8) are reported as `hist: error: ...`, or as `{"error": {"message": ..., "code": "error"}}` with `--json`,
  with exit status 1, instead of a traceback.
- With `--json`, a command-line usage error is printed as `{"error": {"message": ..., "code": "usage"}}` on standard
  error, with exit status 2.
- The notice about moving old backups is no longer printed before `--json` output.
- `hist stop` no longer fails with a traceback when the recorded process no longer exists or belongs to another
  user, and it reports "Nothing is running" for a stale or invalid process id.
- A second SIGINT or SIGTERM stops `watch` and `convert` at once, whichever signal came first.
- `hist catalog list --json` no longer fails for an album whose files are outside the library folder.
- `hist stop` and the other commands that look for the running process only read the lock file; they no longer take
  the lock for a moment, which could make a concurrent writer fail with the code `locked`.
- A malformed `dates.json` (invalid JSON, wrong structure, an invalid date, or a date before 1970) is reported as a
  dates error with a clear message instead of a raw exception. Dates before 1970 are now refused when they are
  read or set, not only when they are applied.
- A tab in a track or album name no longer breaks the reading of the Music app's answers; the scripts now separate
  fields with the ASCII unit separator.
- `hist evacuate` removes only the entries of the album by its own album artist; an album of the same name by
  another artist is left alone.
- `hist evacuate` moves a folder to the evacuation folder even when that is on another volume.
- `dates apply` no longer touches the album folder twice.
- The conversion no longer leaves a half-written file under its final name. The ALAC output, the copy of the store
  file and the rebuilt container of a store file are written to a hidden temporary name and moved into place in one
  step, so a scan of the download folders never takes an unfinished file for an album.
- The cleanup of M4A files left by an interrupted run finds FLAC and M4A files whose suffix is in upper case (for
  example `.FLAC`), skips hidden files, and no longer fails on a folder without FLAC files.
- `hist verify` and the library follower identify an album by its name and its artist, not by its name alone, and
  `hist verify` no longer rebuilds a set for every track, so it is fast on a large library.
- `hist catalog set` and `hist catalog unset` now apply the checks of `hist catalog edit`. Before, `catalog set
  ALBUM TrackNumber abc` stored a value that later crashed the commands that read the track number.
- A `tracks.json` that is not valid JSON, or has malformed tracks, is reported as a catalog error instead of a
  traceback, and `hist catalog check` lists it as a problem. Records without an album name or with a track number
  that is not a number no longer crash album selection and the check.
- `hist catalog add` rejects a spec with duplicate disc and track pairs, a disc above `discs`, a release that is
  not a real `YYYY-MM-DD` date, or an album name that the catalog already uses for a different album artist (it
  used to replace that album silently).
- Tag names are matched ignoring case against the known spellings, so `catalog set ALBUM genre Soul` sets
  `ItemList:Genre` instead of creating `ItemList:genre`.
- `tracks.json`, `dates.json`, the progress files and covers are written to a temporary file in the same folder,
  synced to disk and renamed, so a crash cannot leave a truncated file. Covers used to be written in place.
- `hist catalog add` and `hist store` find FLAC and M4A files whose suffix is in upper case and ignore hidden
  files such as the `._` files that macOS writes on other file systems.

## [2.4.3] - 2026-11-24

This release changes only how the npm package is published. It is the first release published to npm with Trusted
Publishing. The Python package, the command and its behavior are unchanged from 2.4.2.

### Changed

- The release workflow publishes the npm package `@x96x64/his-story` with npm Trusted Publishing (OpenID Connect)
  instead of the access token in the repository secret `NPM_TOKEN`. The `publish-npm` job uses Node.js 24 and the
  latest npm, and npm attaches a provenance statement to every release again now that the repository is public.
- `docs/releasing.md` describes the trusted publisher to set up on npmjs.com instead of the npm token.
- The repository `x96x64/HIStory` is public, and a ruleset protects the branch `main` against deletion and force
  pushes.

### Migration

- No migration is needed for the catalog, the configuration or the library.
- Upgrade with `npm install -g @x96x64/his-story@latest`, `pip install --upgrade his-story` or
  `pipx upgrade his-story`.
- The npm package page lists a provenance statement that links the package to the release workflow run of this tag.

## [2.4.2] - 2026-11-24

This release is the first one published on npm. The 2.4.1 release reached PyPI, but npm refused its package, so no
npm package of 2.4.1 exists. The Python package, the command and its behavior are unchanged from 2.4.1.

### Fixed

- The release workflow publishes the npm package `@x96x64/his-story` without a provenance statement. In 2.4.1 the
  `publish-npm` job ran `npm publish --provenance`, and npm rejected the upload with
  `E422 Unprocessable Entity - Error verifying sigstore provenance bundle: Unsupported GitHub Actions source
  repository visibility`, because npm accepts provenance only from public repositories. The failure also skipped
  the automatic creation of the 2.4.1 GitHub release, which was created by hand from the same notes.
- `docs/releasing.md` describes the npm step without provenance. Provenance can be turned on again when the
  repository becomes public.

### Migration

- No migration is needed for the catalog, the configuration or the library.
- Install from npm with `npm install -g @x96x64/his-story`; this is the first version available there.
- Users who installed from PyPI can upgrade with `pip install --upgrade his-story` or `pipx upgrade his-story`.

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

[Unreleased]: https://github.com/x96x64/HIStory/compare/v2.5.1...HEAD
[2.5.1]: https://github.com/x96x64/HIStory/compare/v2.5.0...v2.5.1
[2.5.0]: https://github.com/x96x64/HIStory/compare/v2.4.3...v2.5.0
[2.4.3]: https://github.com/x96x64/HIStory/compare/v2.4.2...v2.4.3
[2.4.2]: https://github.com/x96x64/HIStory/compare/v2.4.1...v2.4.2
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
