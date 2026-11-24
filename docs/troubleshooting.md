# Troubleshooting

Run `hist doctor` first: it checks Python, the external tools, the configuration, the catalog, the dates file, the
folders and the free disk space. Add `-v` to any command for more detail. Messages are quoted below as `hist`
prints them; text in capitals or braces stands for a value.

## Setup and Environment

**"there is no catalog in HOME; run 'hist init' to create one, or name an existing one with --home DIR or the HISTORY_HOME variable" (exit 2).**
No `config.toml` or `tracks.json` exists in the catalog folder. Run `hist init`, or point `hist` at your catalog
with `--home DIR` (given before the command) or the `HISTORY_HOME` environment variable.

**"TOOL was not found on PATH; install it, for example with: brew install ffmpeg".**
A required external program is missing. Install `ffmpeg` (which includes `ffprobe`), `flac` (which includes
`metaflac`) and `exiftool` with Homebrew, and `SetFile` with `xcode-select --install`. `hist doctor` also checks
that ffmpeg has the ALAC encoder.

**"... needs macOS (the Music app, osascript or SetFile); this system is ...".**
The command works with the Music app or `SetFile` and cannot run on this system. Catalog commands (`catalog`,
`dates list`, `dates set`, `dates unset`, `doctor`, `agent-help`) work everywhere.

**"HOME already holds a catalog; use --force to replace it", "SRC is not a catalog (no tracks.json)".**
`hist init` does not overwrite a catalog that holds tracks. Use `--force` only when you mean to replace it, and
give `--from` a folder that contains `tracks.json`.

**"config.toml: ..." or "[store] needs both 'album' and 'file'".**
`config.toml` is not valid TOML or lacks a required key. See docs/catalog-format.md for every key.

**"catalog is already running (pid N)" (error code `locked`).**
Another `hist` process is writing the catalog, or a `watch` or `convert` is running. Wait for it, or end it with
`hist stop`. The lock is released by the operating system when the process ends, so a stale lock file is harmless.

## Catalog Errors

**"'TEXT' matches no album; run 'hist catalog list' to see the names".**
Check the spelling, or use text that occurs in the album name.

**"'TEXT' must match exactly one album; it matches: ...".**
Use more of the name, or pass `--exact` with the full name from `hist catalog list --json`.

**"the operations are not valid JSON ..." or "the operations must be a JSON array of objects".**
`hist catalog edit` expects an array, for example `[{"op": "set", "album": "A", "tag": "Genre", "value": "Soul"}]`.
See docs/commands.md for every key. One invalid operation rejects the whole batch, and nothing is written.

**"no operations given: pass FILE, or pipe a JSON array to standard input".**
`catalog edit` never asks questions and fails when standard input is a terminal. Pass a file or pipe the array.

**"X is required on every track" or "X is never stored in the catalog".**
Title, Album, AlbumArtist, Artist, TrackNumber and DiskNumber cannot be removed, and Comment and Encoder are never
stored.

**"N tracks of the spec have no composer decision (null)".**
Replace each `null` composer in the spec with a name, or with `""` for no composer.

**"the first FLAC file has no embedded picture; give the spec a 'cover'" and similar.**
Add `"cover": "image.jpg"` to the spec, or make every FLAC file carry the same picture.

**"FOLDER has N FLAC files but the spec lists M tracks".**
The download is incomplete or the spec is wrong. Compare them with `ls` and the spec's `tracks` list.

## Conversion

**"not every FLAC could be matched to a catalog track; nothing was written".**
The files could not be paired with the album's tracks. Run `hist convert --dry-run --only "Album Name"` to see the
pairing and the durations, and check the aliases and renumber rules in `config.toml`.

**"the M4A does not decode to the same samples as the FLAC", "durations differ ...", "the M4A tags differ from the catalog ...".**
A verification step failed. The FLAC files are kept. Check the disk and the ffmpeg version, then run the
conversion again; files left by an interrupted run are replaced.

**A download does not start converting.**
Run `hist status`. A folder is used only when it holds as many FLAC files as the album has tracks, no
unfinished download files, nothing changed in the last 10 seconds, and every file decodes cleanly. If the album
name of the download differs from the catalog's, add it to `[match.aliases]`. An album is also skipped while free
space would fall below `min_free_gb`.

**A track was paired with the wrong title.**
Titles that contain one another (versions of one song) can be confused. Check the pairing and the durations with
`hist convert --dry-run --only "Album Name"` before converting.

**Re-downloading an album.**
Delete the album's old download folder first, so that old and new files do not mix, and remove the album from
`state/converted.json` if it was converted before.

**The disk filled up.**
Moving files to the Trash does not free space until the Trash is emptied, and system caches can hold many
gigabytes until a restart. `hist convert` skips an album while free space would fall below `min_free_gb`;
`--keep-flac` needs about twice the space.

## Dates

**"'TEXT' is not a date; write it as YYYY-MM-DD" and "dates before 1970 cannot be set".**
Use a date from 1970 on, written `YYYY-MM-DD`.

**"'PATH' must be 'Artist' or 'Artist/Album', relative to the library".**
Give the path as the folders appear in the library, not as an absolute path.

**File dates changed after editing tags.**
Writing tags changes the modification date. Run `hist dates apply` (or `--only "Album Name"`) afterwards.

## The Music App

**"the Music app was quit or stopped responding while hist was using it."**
Commands that read or change the Music app need it running for their whole run. Open the Music app with the usual
library and run the command again; work already done is kept.

**"the Music app did not answer in time (is a permission prompt waiting?)".**
macOS asks once whether your terminal may control the Music app. Allow it in System Settings under Privacy and
Security, Automation, and run the command again.

**"the entries of ALBUM are still listed; the Music app may be showing a confirmation ...".**
Look for a dialog in the Music app and answer it yourself; `hist` never clicks it.

## More Cases

**A synced device shows an album with store artwork, the store's track list or another release's year.**
The files are not the cause when `hist verify --music` passes. Remove the album from the Music app
(`hist evacuate --album "Album Name"`), add it again yourself from the evacuation folder while `hist watch`
runs, and sync the device after each album, one album at a time in release order.

**The Music app shows a dialog while entries are deleted.**
Deleting an entry whose file still exists can ask whether to keep the file. `hist evacuate` moves the files away
first so that no dialog appears. If a dialog does appear, answer it yourself; `hist` never clicks it.

**The Music app refuses to switch libraries ("the current library is in use by a device").**
Eject the device in the Finder and disconnect it; if the device is shown in the Finder over Wi-Fi, turn that off
first. Then hold the Option key while opening the Music app to choose another library. Do not sync a device
while another library is open.

**Removing an album for good.**
Delete the album in the Music app yourself, then run `hist catalog remove "Album Name"` (try `--dry-run` first).
It removes the album from the catalog folder, so that `hist watch`, `hist status` and `hist verify` no longer wait
for it. The library folder and the Music app are not touched.

**A store purchase still counts as purchased.**
Store files carry purchase data in the audio track's description, which no tag editor removes. `hist convert`
rebuilds the container without re-encoding; then `hist store-entries --delete` removes the store version.
