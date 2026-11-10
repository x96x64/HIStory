# hist(1)

## NAME

hist - rebuild an Apple Music library from FLAC downloads with exact, verified metadata

## SYNOPSIS

```
hist [--home DIR] [-q | --quiet] [-v | --verbose] <command> [<args>]
hist --version
hist [<command>] --help
```

## DESCRIPTION

`hist` converts downloaded FLAC albums to Apple Lossless files whose tags equal a catalog. You add the converted
albums to the Music app yourself, one at a time; `hist` checks each album you add and sets the dates of its
folders and files. `hist` never adds anything to the Music app.

Commands that change the Music app or its library folder on request are marked **writes to Music** below. All other
commands write only to the catalog folder and the download folders.

## GLOBAL OPTIONS

`--home DIR`
: The catalog folder. Default: `$HISTORY_HOME`, else `~/Library/Application Support/HIStory`.

`-q`, `--quiet`
: Print warnings and errors only.

`-v`, `--verbose`
: Print more detail.

`--version`
: Print the version and exit.

## COMMANDS

### hist init [--from DIR] [--force]

Create the catalog folder with an example `config.toml`, an empty `tracks.json` and `dates.json`. With `--from`,
copy an existing catalog (`config.toml`, `tracks.json`, `covers/`, `specs/`, `dates.json`) into it and check it.
A catalog that already holds tracks is replaced only with `--force`.

### hist doctor

Check Python, the external tools, the configuration, the catalog, the dates file, the folders, free disk space,
and whether `watch` or `convert` is running. Exits 1 if something required is missing.

### hist status [--music]

Print one line per album, oldest release first: in the library, converted and ready to add, ready to convert, or
what it is waiting for. With `--music`, also count each album's tracks in the Music app.

### hist convert [--only TEXT] [--keep-flac] [--source DIR]... [--dry-run]

Convert every complete download once, oldest release first. For each track: write the catalog's tags and cover
into the FLAC file, convert it to ALAC, check that the M4A decodes to the same samples, has the same duration
(within 0.5 s), carries exactly the catalog's tags and no other metadata, rename it to `NN Title.m4a`
(`D-NN Title.m4a` for several discs), and delete the FLAC file. A download is complete when the folder holds as
many FLAC files as the album has tracks, no unfinished download files, nothing changed in the last 10 seconds,
and every file decodes cleanly.

`--only TEXT`
: Only albums whose name contains TEXT.

`--keep-flac`
: Keep the FLAC files after the checks (needs about twice the space).

`--source DIR`
: Use this download folder instead of the configured ones (repeatable).

`--dry-run`
: Show how the files of each complete download would be paired with the catalog's tracks, with durations.
Nothing is written.

An album is skipped while free space would fall below `min_free_gb`. Files left by an interrupted run are
replaced; a FLAC file is deleted only after its M4A passed every check.

### hist watch [--only TEXT] [--keep-flac] [--source DIR]... [--interval SECONDS] [--log FILE] [--convert-only]

Look at the download folders and the library every 10 seconds.

Downloads: add albums from `specs/` to the catalog when their download is complete, and convert every complete
download as `hist convert` does.

Library: you add the converted albums to the Music app yourself (drag the album folder into the Music window, or
File > Add to Library). When an album appears in the library folder and its files stop changing, `hist watch`
compares its files with the catalog, sets the dates of its artist folder and album folder from `dates.json`, and
records it as added. An album whose files differ from the catalog is reported and not dated. An album that leaves
the library is forgotten and checked again when it is added again. The log names the next album to add, in release
order, and says whether it is converted yet.

`hist watch` ends by itself, with exit status 0, when every album of the catalog is converted and in the library.
Lines are also written to `state/logs/watch.log`.

`--convert-only`
: Do not watch the library; end when every album is converted.

### hist stop

Send SIGTERM to a running `watch` or `convert`. Each finishes the album it is working on, then exits.

### hist dates list | apply | check | script [--only TEXT] [--dry-run]

Folder and file dates in the library, from `dates.json`.

`list`
: Every entry, and whether its folder is in the library.

`apply`
: **Writes to the library folder.** Set the creation and modification dates of every entry whose folder exists.
With `--dry-run`, show what would be set.

`check`
: Check the dates; exits 1 on any mismatch.

`script`
: Print the same work as shell commands, without running them.

`--only TEXT` selects entries whose path contains TEXT; the artist entry of each selected album comes along.

### hist verify [--music] [--downloads] [--path DIR]... [--allow-missing] [--no-decode]

Check the library's M4A files against the catalog: every track present once, tags and cover equal, no Comment or
Encoder tag, a disc number on every track, no unexpected metadata, no store purchase data, no download id in a
file name, every file decodes cleanly, and every album complete. Exits 1 on any problem.

`--music`
: Also check the Music app: no store versions, the right track count per album, and albums added in release order.

`--downloads`
: Also check converted files still in the download folders.

`--path DIR`
: Check this folder instead of the library (repeatable).

`--allow-missing`
: Do not fail because tracks or albums are missing.

`--no-decode`
: Skip decoding every file.

### hist catalog \<action\>

`list`
: The albums, oldest release first, with track counts.

`show ALBUM [--disc N] [--track N]`
: The tracks of an album, or every tag of one track. ALBUM is text contained in the album name.

`set ALBUM TAG VALUE [--disc N] [--track N]`
: Set a tag on every track of an album, or on one track. TAG may omit the group: `Genre` means `ItemList:Genre`.
The previous `tracks.json` is kept in `state/history/`.

`unset ALBUM TAG [--disc N] [--track N]`
: Remove a tag. Title, Album, AlbumArtist, Artist, TrackNumber and DiskNumber cannot be removed.

`add SPEC --from DIR [--dry-run]`
: Add an album from a spec file and the folder of its downloaded FLAC files.

`check`
: Check the catalog files for consistency; exits 1 on any problem.

`import FOLDER`
: Start an empty catalog from the tags of an existing library folder, dropping Comment and Encoder.

### hist retag PATH... [--apply] [--fields LIST] [--prune] [--list-unmatched]

Match the M4A files under each PATH to the catalog and show the tags that differ. With `--apply`, save the
current tags to `state/snapshots/`, then write the catalog's tags. Writing changes the files' dates, so run
`hist dates apply` afterwards for albums in the library, and `hist refresh` for albums in the Music app.

### hist refresh ALBUM

**Writes to Music.** Make the Music app re-read the files of an album (tags, cover and file names). No entry is
added or removed.

### hist evacuate [--album TEXT] [--dry-run]

**Writes to Music.** Move the library folders of the catalog's albums to the `evacuation` folder, then remove
their entries from the Music app. Nothing is deleted from disk. Add them again from that folder in the Music app,
one at a time, while `hist watch` runs.

### hist store-entries [--delete]

List the Music app's entries of the album named in `[store]`, and say which still carry store purchase data.
With `--delete` (**writes to Music**), delete those entries, but only if the cleaned copy made by
`hist convert` equals the catalog and has the same audio as every entry to be deleted.

## EXIT STATUS

| Status | Meaning |
| --- | --- |
| 0 | Success, or everything is done |
| 1 | An error, or a check failed |
| 2 | A usage or configuration error |
| 130 | Stopped by Ctrl-C |
| 143 | Stopped by SIGTERM (`hist stop`) |

## STOPPING

The first Ctrl-C, or `hist stop`, lets `watch` and `convert` finish the album they are working on; while they
are only waiting, they stop at once. A second Ctrl-C stops at once; files left by an interrupted conversion are
replaced by the next run.

## ENVIRONMENT

`HISTORY_HOME`
: The catalog folder, unless `--home` is given.

## FILES

```
<home>/config.toml        settings
<home>/tracks.json        the catalog's tags
<home>/covers/            cover images, named by SHA-256
<home>/specs/             albums to add
<home>/dates.json         folder and file dates
<home>/state/             converted.json, added.json, history/, snapshots/, staging/, logs/, *.lock
```

## EXAMPLES

Convert while downloading, and date each album as you add it to the Music app:

```sh
hist watch
```

Fix a genre and bring an album in the library in line:

```sh
hist catalog set "Album Name" Genre Soul
hist retag "~/Music/Music/Media.localized/Music/Artist/Album Name" --apply
hist refresh "Album Name"
hist dates apply --only "Album Name"
```

## SEE ALSO

docs/catalog-format.md, docs/troubleshooting.md
