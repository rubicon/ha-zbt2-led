# SPDX-License-Identifier: MIT
"""Only the bots themselves get the PR-policy automation exemption."""

from pathlib import Path
import subprocess

import pytest
import yaml

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "pr-policy.yaml"
REPO = "rubicon/ha-zbt2-led"
EXEMPT_JOBS = ("branch-naming", "issue-link")


def _run(job: str, head_ref: str, head_repo: str, author: str) -> int:
    """Run a job's shell step the way GitHub Actions would, return its exit code."""
    script = yaml.safe_load(WORKFLOW.read_text())["jobs"][job]["steps"][0]["run"]
    env = {
        "PATH": "/usr/bin:/bin",
        "HEAD_REF": head_ref,
        "HEAD_REPO": head_repo,
        "BASE_REPO": REPO,
        "AUTHOR": author,
        "PR_BODY": "",
    }
    return subprocess.run(
        ["bash", "-e", "-c", script], env=env, capture_output=True, check=False
    ).returncode


@pytest.mark.parametrize("job", EXEMPT_JOBS)
@pytest.mark.parametrize(
    ("head_ref", "author"),
    [
        ("dependabot/pip/zha-2.4.3", "dependabot[bot]"),
        ("release-please--branches--main", "rubicon-release-please[bot]"),
    ],
)
def test_bot_pr_from_this_repo_is_exempt(job: str, head_ref: str, author: str) -> None:
    """A bot's own PR passes without a dev/ branch or an issue link."""
    assert _run(job, head_ref, REPO, author) == 0


@pytest.mark.parametrize("job", EXEMPT_JOBS)
@pytest.mark.parametrize(
    ("head_ref", "head_repo", "author"),
    [
        ("release-please--branches--main", "someone/ha-zbt2-led", "someone"),
        ("dependabot/pip/zha-2.4.3", "someone/ha-zbt2-led", "someone"),
        ("release-please--branches--main", REPO, "maintainer"),
        ("dependabot/pip/zha-2.4.3", REPO, "maintainer"),
        ("feature", REPO, "dependabot[bot]"),
        ("feature", REPO, "rubicon-release-please[bot]"),
    ],
)
def test_bot_branch_name_alone_is_not_exempt(
    job: str, head_ref: str, head_repo: str, author: str
) -> None:
    """A fork or a person cannot claim the exemption by naming a branch."""
    assert _run(job, head_ref, head_repo, author) == 1
