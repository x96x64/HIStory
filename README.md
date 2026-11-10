# HIStory

HIStory (`hist`) helps you rebuild an Apple Music library on macOS from FLAC downloads, so that every track ends
up as an Apple Lossless (ALAC) file whose tags and cover are exactly the ones you decided on.

It keeps a **catalog** of the exact tags of every track. When a download arrives, `hist` writes the catalog's tags
into the FLAC files, converts them to ALAC with ffmpeg, checks every result, and only then deletes the FLAC
files. **You add the converted albums to the Music app yourself**, one at a time in release order, syncing your
device after each one. `hist` notices each album you add, checks it against the catalog, and sets the dates of
its folder and files.

- `hist` never adds anything to the Music app. Adding albums is always your step.
- The audio is never altered: each M4A decodes to exactly the same samples as its FLAC.
- Every converted file is checked against the catalog: tags, cover, duration, and no stray metadata.
- `hist watch` starts on its own as downloads complete and stops by itself when every album is converted and in
  your library. It can be stopped safely at any time.

## Requirements

- macOS with the Music app
- Python 3.12 or newer
- [Homebrew](https://brew.sh) packages: `ffmpeg`, `flac`, `exiftool`, `pipx`
- The Xcode command line tools (for `SetFile`): `xcode-select --install`

## Installation

Unpack the ZIP, then:

```sh
brew install ffmpeg flac exiftool pipx
pipx ensurepath                      # then open a new Terminal window
pipx install ~/Downloads/HIStory-1.0.0
```

Use the path where you unpacked the ZIP. After installing, `hist` works in any folder, and the unpacked folder
is no longer needed. `pipx install` builds the package and needs a network connection the first time. To install
without one, use the wheel in `dist/`:

```sh
pipx install ~/Downloads/HIStory-1.0.0/dist/history_music-1.0.0-py3-none-any.whl
```

To upgrade, run `pipx install --force` with the new folder.

## Quick start

```sh
hist init --from ./my-catalog   # or 'hist init' for an empty catalog
hist doctor                     # check tools, settings and catalog
hist watch                      # leave it running
```

While `hist watch` runs:

1. Download the albums into the download folder. Each complete download is converted; the log says
   "Next album to add to the Music app: ... (converted, ready to add)".
2. Add that album to the Music app yourself: drag its folder from the download folder into the Music window, or
   use File > Add to Library. `hist watch` notices it, checks it, and sets its dates.
3. Sync your device, then add the next album.

When every album is converted and in the library, `hist watch` ends by itself. Finish with:

```sh
hist verify --music             # final check of the library and the Music app
```

## Commands

| Command | Description |
| --- | --- |
| `hist init [--from DIR]` | Create the catalog folder, or copy an existing catalog into it |
| `hist doctor` | Check the tools, the configuration and the catalog |
| `hist status [--music]` | Show how far each album has come |
| `hist convert [--dry-run]` | Convert every complete download once |
| `hist watch [--convert-only]` | Convert downloads and date the albums you add; ends when everything is done |
| `hist stop` | Ask a running `watch` or `convert` to stop after the current album |
| `hist dates list\|apply\|check\|script` | Folder and file dates in the library |
| `hist verify [--music]` | Check the library against the catalog |
| `hist catalog list\|show\|set\|unset\|add\|check\|import` | Read and edit the catalog |
| `hist retag PATH... [--apply]` | Write the catalog's tags back into existing files |
| `hist refresh ALBUM` | Make the Music app re-read an album's files |
| `hist evacuate [--dry-run]` | Move albums out of the library so that you can add them again |
| `hist store-entries [--delete]` | Remove the store version of an album bought in the Music app |

See [docs/commands.md](docs/commands.md) for every option, exit status and file.

## Configuration

The catalog lives in `~/Library/Application Support/HIStory` unless `--home DIR` or the `HISTORY_HOME`
environment variable says otherwise. It holds `config.toml` (folders and matching rules), `tracks.json`
(the tags of every track), `covers/`, `specs/` (albums to add) and `dates.json`. Progress records and logs are
kept in its `state/` folder.

See [docs/catalog-format.md](docs/catalog-format.md) for the format of every file, and
[docs/troubleshooting.md](docs/troubleshooting.md) for known issues.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

The tests generate short FLAC files with ffmpeg and never touch your library or the Music app.

## License

MIT. See [LICENSE](LICENSE).
