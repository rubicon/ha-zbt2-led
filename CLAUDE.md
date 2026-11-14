# CLAUDE.md

Agent instructions for `rubicon/ha-zbt2-led`, a Home Assistant custom integration (domain `zbt2_led`) that exposes the Home Assistant Connect ZBT-2's RGB LED as `light.zbt2_led`.

## Repository rules

- Every change starts with an issue, gets a `dev/<issue>-<slug>` branch in its own worktree under `worktrees/`, and merges through a squash PR whose body says `Closes #N`. CI enforces the branch name, the Conventional Commits PR title and every commit message.
- Commits are signed. `main` requires signed commits, linear history and the CI checks listed in branch protection.
- No AI-authorship trailers or "Generated with" lines in commits, PR bodies or files.
- Releases are cut by release-please from `main`. Never bump `manifest.json`'s version by hand.

## Development

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/ruff check .
.venv/bin/black --check .
.venv/bin/pytest
```

Test output must be clean: `pyproject.toml` turns warnings into errors and requires 95% coverage.

See ARCHITECTURE.md for the module layout.
