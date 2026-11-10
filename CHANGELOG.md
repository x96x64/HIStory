# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
