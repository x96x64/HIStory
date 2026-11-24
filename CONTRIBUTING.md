# Contributing

Thank you for helping with HIStory. This guide describes how to set up the project, what a change must contain and
how releases are made. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

## Development Setup

HIStory needs Python 3.12 or newer and uses only the standard library at run time.

```sh
git clone https://github.com/x96x64/HIStory.git
cd HIStory
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pre-commit install   # optional; needs `pip install pre-commit`
```

## Tests and Style

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Use `ruff check --fix .` and `ruff format .` to correct what can be corrected automatically. Lines are at most 120
characters. Tests that need `ffmpeg`, `flac` or `exiftool` skip themselves when the tools are missing, and no test
touches a real Music app or catalog. Add or update tests for every change.

The npm wrapper in `npm/` is checked by `tests/test_npm.py` when Node.js 18 or newer is installed.

## Commit Messages

Commits follow [Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/):
`type(scope): subject`. The types are `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`,
`chore` and `revert`. Write the subject in the imperative mood, in lowercase, without a final period. Mark a breaking
change with `!` after the type or with a `BREAKING CHANGE:` footer. Examples:

```text
feat(catalog): add a cover command
fix(retag): keep the disc number when a track has no total
docs: describe the --json output
ci: run the tests on Python 3.13
feat(config)!: rename the library key
```

CI checks the messages of every pull request with commitlint.

## Branches and Pull Requests

1. Create a branch from `main`, for example `feat/catalog-cover`.
2. Keep each commit to one logical change.
3. Update `docs/commands.md` and the section Unreleased of `CHANGELOG.md` with every change of behavior.
4. Open a pull request against `main`. CI must pass (ruff, pytest, commitlint) before it is merged.

## Releases

Maintainers release as described in [docs/releasing.md](docs/releasing.md). In short: bump the version in
`pyproject.toml` and `npm/package.json`, move the Unreleased entries of the changelog under the new version, commit
with `chore(release): X.Y.Z`, tag `vX.Y.Z` and push the tag. The release workflow tests, builds and publishes to PyPI
and npm and creates the GitHub Release.
