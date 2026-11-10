# Catalog format

The catalog folder (see `hist --help` for where it is) holds the exact metadata that every track must end up
with. Edit it with `hist catalog` where possible; the files are plain JSON and TOML and can also be edited by hand
or with the help of an assistant. Run `hist catalog check` after editing.

```
config.toml
tracks.json
covers/<sha256>
specs/<name>.json
dates.json
state/                 created by hist; not part of the catalog
```

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

Paths may start with `~`. A relative path is taken relative to the catalog folder.

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

Every change made by `hist catalog set`, `unset` or `remove` keeps the previous file in `state/history/`.

## specs/

A spec describes an album to add. `hist watch` adds it to the catalog as soon as its download is complete, and
`hist catalog add SPEC --from DIR` adds it at once. After that, the catalog is what counts: a spec is never
applied again.

```json
{
 "album": "Album Name",
 "album_artist": "Artist",
 "release": "2001-02-03",
 "discs": 1,
 "copyright": "℗ 2001 Example Records",
 "cover": "covers/<sha256>",
 "tracks": [
  {"disc": 1, "track": 1, "title": "Song Title", "artist": "Artist",
   "composer": "First Writer, Second Writer", "genre": "Pop"}
 ]
}
```

`cover`
: Optional. An image file (JPEG or PNG), relative to the catalog folder or absolute. Without it, the picture
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
