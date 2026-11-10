# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] - 2026-11-10

### Changed

- The distribution name is `hist`, the same as the command and the Python package, instead of `history-music`.
  Remove the old installation with `pipx uninstall history-music` before `pipx install ./HIStory`.
- HIStory is kept locally and installed from its folder.

### Removed

- The online test workflow, the README badges and the project URLs. Run the tests locally with
  `python -m pytest`.

## [2.2.0] - 2026-11-10

### Changed

- Backups are kept in one place, `state/backups/`, with one folder per command named
  `<time>-<command>`, for example `20261110-210045-catalog-remove`. It holds every file the command changed:
  `tracks.json`, `dates.json` and removed covers for `hist catalog set`, `unset`, `add`, `remove` and `import`,
  and the files' current tags for `hist retag --apply`.
- The first `hist` command after the update moves the copies in `state/history/` and the folders in
  `state/snapshots/` into `state/backups/`, and removes the old folders when they are empty.

## [2.1.0] - 2026-11-10

### Changed

- The Python package is named `hist`, after the command, instead of `history_music`; `python -m hist` runs the
  command. The command and the distribution name `history-music` are unchanged.
- The package metadata, the command line help and `docs/commands.md` describe the project with one shared sentence.

## [2.0.0] - 2026-11-10

### Changed

- A relative `cover` in a spec file is taken relative to the spec file's folder instead of the catalog folder.

### Removed

- The `specs/` folder of the catalog. `hist watch` no longer adds albums from it, and `hist init`,
  `hist doctor` and `hist catalog check` no longer look for it. Add a new album with
  `hist catalog add SPEC --from DIR`; the spec file can be kept anywhere.

## [1.2.0] - 2026-11-10

### Changed

- `hist verify` reads metadata atoms and store purchase data for up to 40 files per exiftool run instead of one
  file per run, which makes it several times faster on a full library.
- Build output is no longer kept in the project.
- The license's copyright line uses the sign ©.

### Removed

- Migration of state files from the tool that preceded 1.0.0 (`registered.json`, progress files stored as lists).

## [1.1.0] - 2026-11-10

### Added

- `hist catalog remove ALBUM [--dry-run]`: removes an album you removed from the Music app from the catalog
  folder, with its `dates.json` entries, progress records, spec and unused covers. The previous files are kept in
  `state/history/`.

### Changed

- Every error that `hist` reports without a traceback now derives from one base class, `HistError`.
- `hist dates` is split into one function per action; the output is unchanged.

### Fixed

- `hist doctor` reports a `tracks.json` that is not valid JSON instead of stopping with a traceback.

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
