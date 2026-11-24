# Releasing

This document is for maintainers. A release publishes the package `his-story` to PyPI and the package
`@x96x64/his-story` to npm and creates a GitHub Release. The command is `hist` in both.

## One-Time Setup

1. PyPI Trusted Publishing: on pypi.org, open the project (or "Publishing" in the account settings for a new
   project) and add a GitHub publisher with owner `x96x64`, repository `HIStory`, workflow `release.yml` and
   environment `pypi`.
2. GitHub environment: in the repository settings, create the environment `pypi`. Optionally require a reviewer.
3. npm token: on npmjs.com, create an automation (granular) access token that can publish `@x96x64/his-story`,
   and store it as the repository secret `NPM_TOKEN`.

## Procedure

1. Make sure `main` is green in CI and the section Unreleased of `CHANGELOG.md` lists every change.
2. Choose the version `X.Y.Z` following [Semantic Versioning](https://semver.org/).
3. Set the version in `pyproject.toml` and in `npm/package.json`.
4. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`, add an empty `## [Unreleased]` above
   it, and update the comparison links at the bottom.
5. Run the checks:

   ```sh
   python scripts/check_versions.py
   python scripts/release_notes.py X.Y.Z   # prints the release notes
   .venv/bin/ruff check . && .venv/bin/ruff format --check .
   .venv/bin/python -m pytest -q
   .venv/bin/python -m build
   (cd npm && npm pack --dry-run)
   ```

6. Commit with `chore(release): X.Y.Z`, then tag and push:

   ```sh
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin main vX.Y.Z
   ```

7. The workflow `release.yml` runs on the tag. It checks that the tag, `pyproject.toml`, `npm/package.json` and the
   changelog name the same version, runs the tests on macOS, builds the sdist and wheel, publishes to PyPI with
   Trusted Publishing, publishes to npm with provenance, and creates the GitHub Release with the notes written by
   `scripts/release_notes.py` (see Release Notes).
8. Check that `pip install his-story==X.Y.Z` and `npm install -g @x96x64/his-story@X.Y.Z` provide `hist --version`.

## Release Notes

- The release notes are the section of the version in `CHANGELOG.md`, verbatim and without its `## [X.Y.Z]` heading,
  then a blank line, then `**Full Changelog**: <compare URL>`. The URL is the link reference `[X.Y.Z]: ...` at the
  bottom of the changelog. The format is fixed; do not write the notes anywhere else.
- `python scripts/release_notes.py X.Y.Z` prints the notes, and the workflow `release.yml` uses the same script. It
  fails when the section or its link reference is missing or the section is empty. Run it before you tag.
- Write the notes of each version as completely and in as much detail as possible: every user-visible change in its
  category (Added, Changed, Deprecated, Removed, Fixed, Security), and for a breaking change what to run to migrate.
- Once a version is released (tagged), its `CHANGELOG.md` section and its GitHub release notes are never edited
  again. Put a correction into the notes of a later version. The release is created with `gh release create`, which
  fails when the release already exists; do not use `gh release edit` or `--clobber`.

## If a Release Fails

A version that reached PyPI or npm cannot be replaced. Fix the problem, use the next patch version and release again.
If only a later job failed, re-run that job from the Actions page.
