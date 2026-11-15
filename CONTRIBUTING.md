# Contributing

Thanks for your interest in contributing. The workflow is small and strict so `main` always stays releasable.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Workflow

1. **Open an issue first** describing the bug or change and why it matters.
2. **Branch** from `main` as `dev/<issue-number>-<short-kebab-description>`, for example `dev/42-fix-flash-timing`.
3. **Commit** using [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) (`feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `build`, `chore`). Commits to `main` must be signed.
4. **Open a pull request** into `main` with `Closes #N` in the body. CI must pass before merge.

## Development

Requires Python 3.14.

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
```

## Verification (run before opening a PR)

```bash
.venv/bin/ruff check .
.venv/bin/black --check .
.venv/bin/pytest
```

The test run treats warnings as errors and requires 95% coverage. CI runs the same commands plus hassfest and HACS validation.

## Releases

release-please opens a release PR from `main` and writes the entry in `CHANGELOG.md`, creating the file with the first release. Only `feat`, `fix`, `perf` and `revert` commits appear there, so a release is proposed only once one of those lands. Edit the entry in the release PR before merging it. Never bump `manifest.json`'s version by hand.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md).
