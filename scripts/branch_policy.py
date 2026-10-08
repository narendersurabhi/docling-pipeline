"""Branch policy for pull requests (constitution VIII: one feature, one branch).

    spec/NNN-short-name   a feature. specs/NNN-short-name/ must exist with spec.md,
                          plan.md and tasks.md, and every task must be ticked before merge.
    fix/<name>            a bug fix (cite the violated requirement ID in the PR).
    chore/<name>          tooling, CI, dependencies, refactors without behaviour change.
    docs/<name>           documentation only. May not touch src/ or tests/.

Usage: python scripts/branch_policy.py <branch> [<changed file> ...]
Exit code 1 with a message per violation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANCH = re.compile(r"^(?P<kind>spec|fix|chore|docs)/(?P<rest>[a-z0-9][a-z0-9._-]*)$")
SPEC_BRANCH = re.compile(r"^(?P<num>\d{3})-[a-z0-9][a-z0-9-]*$")
SPEC_FILES = ("spec.md", "plan.md", "tasks.md")


def violations(branch: str, changed: list[str], root: Path = ROOT) -> list[str]:
    m = BRANCH.match(branch)
    if not m:
        return [f"branch '{branch}' must be spec/NNN-name, fix/<name>, chore/<name> or docs/<name>"]
    kind, rest = m["kind"], m["rest"]
    problems = []

    if kind == "spec":
        if not SPEC_BRANCH.match(rest):
            return [f"feature branch '{branch}' must look like spec/NNN-short-name"]
        spec_dir = root / "specs" / rest
        if not spec_dir.is_dir():
            return [f"spec branch '{branch}' needs specs/{rest}/ (copy specs/_template/)"]
        problems += [
            f"specs/{rest}/{name} is missing"
            for name in SPEC_FILES
            if not (spec_dir / name).is_file()
        ]
        tasks = spec_dir / "tasks.md"
        if tasks.is_file():
            open_tasks = [
                line.strip()
                for line in tasks.read_text(encoding="utf-8").splitlines()
                if line.lstrip().startswith("- [ ]")
            ]
            problems += [f"unfinished task in specs/{rest}/tasks.md: {t}" for t in open_tasks]

    if kind == "docs":
        code = [f for f in changed if f.startswith(("src/", "tests/"))]
        problems += [f"docs branch changes code: {f}" for f in code]

    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    branch, changed = argv[0], argv[1:]
    problems = violations(branch, changed)
    for p in problems:
        print(f"::error::{p}")
    if not problems:
        print(f"branch policy OK: {branch}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
