# CLAUDE.md

Agent instructions for `rubicon/ha-zbt2-led`, a Home Assistant custom integration (domain `zbt2_led`) for the Home Assistant Connect ZBT-2's RGB LED.

## Repository rules

- Every change starts with an issue, gets a `dev/<issue>-<slug>` branch in its own worktree under `worktrees/`, and merges through a squash PR whose body says `Closes #N`. CI enforces the branch name, the Conventional Commits PR title and every commit message.
- Commits are signed. Branch protection on `main` requires signed commits, linear history and the CI checks.
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

## Code rules

- Only `zha_link.py` may touch ZHA or bellows internals. Every access there is checked and raised as a `LedLinkError` subclass; nothing else imports from `homeassistant.components.zha` or `bellows`.
- Never crash on a link failure. The controller turns errors into availability and repair issues; the driver never raises.
- Never send faster than `MIN_FRAME_INTERVAL`. Timing belongs to `driver.py`; effects only describe frames.
- An off light under the default idle behaviour must send nothing after a Home Assistant or ZHA restart. Tests cover this; keep them.
- Tests drive ZHA through `tests/conftest.py` (`start_zha` and `stop_zha`) and the firmware double in `tests/firmware.py`, which decodes frames independently of the integration. Wire bytes in tests are literal.
- Timers run on the event loop's real clock. Use the `advance` helper in `tests/conftest.py`, not `freezer`, to move effects forward.
- Unload every config entry a test sets up, so no timer outlives the test.
