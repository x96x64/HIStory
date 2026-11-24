# Releasing

This document is for maintainers. A release publishes the package `his-story` to PyPI and to npm and creates a GitHub
Release. The command is `hist` in both.

## One-Time Setup

1. PyPI Trusted Publishing: on pypi.org, open the project (or "Publishing" in the account settings for a new
   project) and add a GitHub publisher with owner `x96x64`, repository `HIStory`, workflow `release.yml` and
   environment `pypi`.
2. GitHub environment: in the repository settings, create the environment `pypi`. Optionally require a reviewer.
3. npm token: on npmjs.com, create an automation (granular) access token that can publish `his-story`, and store it
   as the repository secret `NPM_TOKEN`.

## Procedure

1. Make sure `main` is green in CI and the section Unreleased of `CHANGELOG.md` lists every change.
2. Choose the version `X.Y.Z` following [Semantic Versioning](https://semver.org/).
3. Set the version in `pyproject.toml` and in `npm/package.json`.
4. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`, add an empty `## [Unreleased]` above
   it, and update the comparison links at the bottom.
5. Run the checks:

   ```sh
   python scripts/check_versions.py
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
   Trusted Publishing, publishes to npm with provenance, and creates the GitHub Release with the changelog section as
   its notes.
8. Check that `pip install his-story==X.Y.Z` and `npm install -g his-story@X.Y.Z` provide `hist --version`.

## If a Release Fails

A version that reached PyPI or npm cannot be replaced. Fix the problem, use the next patch version and release again.
If only a later job failed, re-run that job from the Actions page.
