"""The CI workflow file is part of the repo, so its triggers are tested like code."""

import re
from pathlib import Path

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"


# AUD-9: CI ran on push only, so a pull request from a fork or a branch without a push
# trigger was never checked.


def test_aud9_ci_runs_on_push_and_on_pull_request():
    line = next(line for line in WORKFLOW.read_text().splitlines() if line.startswith("on:"))
    triggers = set(re.findall(r"[a-z_]+", line.removeprefix("on:")))
    assert {"push", "pull_request"} <= triggers
