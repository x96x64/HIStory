# Maintaining HIStory

HIStory is developed in `~/.HIStory/HIStory`, a local Git repository. The Finder hides `~/.HIStory`; press
Command-Shift-Period in the Finder to show it. The catalog itself lives in `~/Library/Application Support/HIStory`.

```
~/.HIStory/
  HIStory/     the source, a local Git repository
  .book        the number of the last backup (see Backups)
```

## Ground Rules

- You always add albums to the Music app yourself. Do not add a feature that makes `hist` add albums.

## Development

```sh
cd ~/.HIStory/HIStory
python3 -m venv .venv && .venv/bin/pip install -e '.[test]' build pyflakes
.venv/bin/pytest && .venv/bin/python -m pyflakes hist tests
```

## Commits

Write every commit message the same way: an imperative subject of at most 50 characters with no final period, a
blank line, and a body of plain sentences wrapped at 72 characters that says what changed and why.

Claude takes part in every commit. A commit whose changes Claude wrote is made with
`git commit --author="Claude <noreply@anthropic.com>"` and ends with
`Co-Authored-By: x96x64 <284582852+x96x64@users.noreply.github.com>`. Any other commit, such as a version-only
release, has x96x64 as its author and ends with `Co-Authored-By: Claude <noreply@anthropic.com>`.

## Releasing

1. Raise the version in `pyproject.toml` and `hist/__init__.py`, add an entry to `CHANGELOG.md`, and
   commit it as "Release <version>".
2. Run the tests and pyflakes (see Development), then tag the commit:
   `git tag -a v<version> -m "HIStory: v<version>"`.
3. Install it with `pipx install --force ~/.HIStory/HIStory`, delete `HIStory/build`, and run `hist doctor` and
   `hist verify --music`.
4. Make a backup (see Backups).

## Backups

There is no backup script: when a backup is wanted, an AI agent makes it by hand, after every change to the
catalog or the source. Both exist only on this Mac and in these backups.

Every backup is one book of HIStory, numbered in Roman numerals: the first is
`HIStory - PAST, PRESENT AND FUTURE - BOOK I.zip`, then `BOOK II`, `BOOK III`, `BOOK IV`, and so on. The
number of the last book is kept in `~/.HIStory/.book` as a plain decimal number (for example `3` after
`BOOK III`); if the file does not exist, no book has been made yet.

1. Make sure `hist watch` and `hist convert` are not running, and that `hist catalog check` passes.
2. Read the number N in `~/.HIStory/.book` (0 if it does not exist), and write N + 1 back to it.
3. Write one ZIP, `~/Downloads/HIStory - PAST, PRESENT AND FUTURE - BOOK <N + 1 in Roman numerals>.zip`, holding
   two folders: the catalog (`~/Library/Application Support/HIStory`, as `HIStory/`) and `~/.HIStory` (as
   `.HIStory/`). Leave out `.venv`, `build`, `__pycache__`, `.pytest_cache`, `*.lock` and `.DS_Store`; keep
   `.git`, `hist.egg-info` and `.book`. If a ZIP of that name already exists, stop and ask the user.
4. List the ZIP and check that it holds `HIStory/tracks.json`, `HIStory/covers/`,
   `.HIStory/HIStory/docs/maintenance.md` and `.HIStory/.book`.
5. Set the dates of the ZIP file itself, and only of it, to 1995-06-20 00:00:00.00 local time: the
   modification date with `touch -t 199506200000.00 ZIP` and the creation date with
   `SetFile -d "06/20/1995 00:00:00" ZIP`. The files inside the ZIP keep their own dates.

The user puts the ZIP on Google Drive.
