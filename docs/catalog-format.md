# Catalog format

The catalog folder is chosen by `--home DIR`, else `$HISTORY_HOME`, else `~/Library/Application Support/HIStory`. It holds the exact metadata that every track must end up
with. Edit it with `hist catalog` and `hist dates`; the files are plain JSON and TOML, and `config.toml` may be edited
by hand. Run `hist catalog check` after any edit.

```
config.toml
tracks.json
covers/<sha256>
dates.json
state/                 created by hist; not part of the catalog
```

`format` in `tracks.json` is the file format version; `hist` reads only the version it knows (currently 2) and
otherwise reports "unsupported format". Files are UTF-8 JSON; `hist` writes them atomically.

The `state/` folder holds `converted.json` and `added.json` (each maps an album name to `{"time": "YYYY-MM-DDTHH:MM:SS", ...}`),
`backups/`, `staging/`, `logs/` and `*.lock` files. It can be deleted safely when nothing is running; `hist` then
treats every album as not yet converted and not yet added.

## config.toml

```toml
[paths]
downloads = ["~/Music/Downloads"]      # folders that receive downloaded albums, one sub-folder per album
library = "~/Music/Music/Media.localized/Music"
auto_add = "~/Music/Music/Media.localized/Automatically Add to Music.localized"
evacuation = "~/Music/HIStory Evacuated"

[convert]
min_free_gb = 10                       # never let a conversion bring free space below this

[store]                                # optional: one album bought in the Music app's store
album = "Album Name"
file = "Artist/Album Name/01 Song.m4a" # where the Music app keeps it, relative to the library

[match.aliases]                        # optional: download album names that differ from the catalog's
"Album Name in the Catalog" = "Album Name of the Download"

[match.renumber."Album Name in the Catalog"]   # optional: a download that is one disc of a larger set
disc = 1                               # the disc in the catalog
offset = 88                            # downloaded track number minus catalog track number
```

Paths may start with `~`. A relative path is taken relative to the catalog folder. A missing `config.toml` gives
the defaults shown above, with no download folders. `[store]` needs both `album` and `file`, and
`[match.renumber."Album"]` needs both `disc` and `offset`; otherwise `hist` reports a configuration error (exit
status 2). `hist init` writes a complete, commented `config.toml`.

Download folders are matched to catalog albums by album and artist name (one may contain the other) and by the
number of files. When a folder's album name contains the name of a different album, the album whose name fits
better wins.

The store file is never changed in place: `hist convert` copies it to `state/staging/`, rebuilds its container
without re-encoding (which drops the purchase data), and writes the catalog's tags.

## tracks.json

```json
{
 "format": 2,
 "tracks": [
  {
   "file": "Artist/Album Name/01 Song Title.m4a",
   "tags": {
    "ItemList:Title": "Song Title",
    "ItemList:Artist": "Artist",
    "ItemList:AlbumArtist": "Artist",
    "ItemList:Composer": "First Writer, Second Writer",
    "ItemList:Album": "Album Name",
    "ItemList:Genre": "Pop",
    "ItemList:Copyright": "℗ 2001 Example Records",
    "ItemList:TrackNumber": "1 of 12",
    "ItemList:DiskNumber": "1 of 1",
    "ItemList:ContentCreateDate": "2001:02:03 00:00:00Z"
   },
   "blobs": {"ItemList:CoverArt": ["<sha256 of the image in covers/>"]}
  }
 ]
}
```

`file`
: The track's path inside the library, as the Music app names it: `Artist/Album/NN Title.m4a`, or
`D-NN Title.m4a` for albums of several discs. The Music app writes `:` in folder names as `_`.

`tags`
: Every tag the file must carry, with its exiftool group. No other tag is allowed in the file.

`blobs`
: Binary tags, by SHA-256. The image itself is in `covers/<sha256>`.

Rules:

- `ItemList:Title`, `Artist`, `AlbumArtist`, `Album`, `TrackNumber`, `DiskNumber` and `ContentCreateDate` are
  required on every track.
- `TrackNumber` counts within the disc: `N of <tracks on that disc>`.
- `DiskNumber` is on every track: `1 of 1` for a single disc, `N of <number of discs>` otherwise.
- `ContentCreateDate` is the album's release date, the same on every track, written `YYYY:MM:DD 00:00:00Z`.
- `Comment` and `Encoder` are never stored.
- A track without a composer has no `ItemList:Composer` key (not an empty string).
- An album uses one genre for all its tracks; the Music app shows a mixed album under its first track's genre.
- Text inside `()` belongs to the title; a second qualifier after one in `()` goes in `[]`, for example
  `Song (feat. Guest) [Live]`.

Every change made by `hist catalog set`, `unset`, `edit`, `cover`, `add`, `remove` or `import` keeps the previous files in a new folder
`state/backups/<time>-<command>/`, for example `state/backups/20261110-210045-catalog-remove/`.

## Spec files

A spec file describes an album to add. It is not part of the catalog folder: keep it anywhere, and add the album
with `hist catalog add SPEC --from DIR` once its download is complete. From then on the catalog is what counts,
and the spec file is no longer needed.

```json
{
 "album": "Album Name",
 "album_artist": "Artist",
 "release": "2001-02-03",
 "discs": 1,
 "copyright": "℗ 2001 Example Records",
 "cover": "cover.jpg",
 "tracks": [
  {"disc": 1, "track": 1, "title": "Song Title", "artist": "Artist",
   "composer": "First Writer, Second Writer", "genre": "Pop"}
 ]
}
```

`cover`
: Optional. An image file (JPEG or PNG), relative to the spec file's folder or absolute. Without it, the picture
embedded in the first FLAC file is used, and every file must carry the same picture.

`composer`
: Required on every track. `""` means no composer; `null` means not decided yet, and the album is not added.

`copyright`
: For the album; a track may override it with its own `copyright`.

Any other key (for example `source` or `notes` on a track) is ignored and can record where a value came from.

## dates.json

```json
{
 "entries": [
  {"kind": "artist", "path": "Artist", "date": "1990-01-01"},
  {"kind": "album", "path": "Artist/Album Name", "date": "2001-02-03"}
 ]
}
```

`hist watch` (for each album you add) and `hist dates apply` set each folder's creation and modification
dates. An `album` entry covers
the album folder, its sub-folders and every `.m4a` and `.m4v` file inside; an `artist` entry covers the artist
folder only, and is applied before each of its albums. `path` is relative to the library and uses the folder names
the Music app gives (`:` becomes `_`). Dates before 1970 cannot be set. Entries for folders that are not in the
library are skipped, so the file may list albums that are added later.

Edit the file with `hist dates set PATH DATE [--kind album|artist]` and `hist dates unset PATH` (each keeps a
backup), not by hand. `DATE` is `YYYY-MM-DD`. The same applies to `tracks.json`: change it with `hist catalog edit`, `set`, `unset` and `cover`. `hist catalog
export ALBUM` writes an album back as a spec file.
