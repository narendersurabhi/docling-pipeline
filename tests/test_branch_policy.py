"""Constitution VIII: one feature, one branch. Process tooling, so no spec IDs to cite."""

from pathlib import Path

import pytest
from branch_policy import violations


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    spec = tmp_path / "specs" / "004-search-api"
    spec.mkdir(parents=True)
    for name in ("spec.md", "plan.md"):
        (spec / name).write_text("x")
    (spec / "tasks.md").write_text("- [x] T001 done\n")
    return tmp_path


@pytest.mark.parametrize(
    "branch", ["spec/004-search-api", "fix/chunk-ids", "chore/bump-docling", "docs/readme"]
)
def test_valid_branches(repo, branch):
    assert violations(branch, ["README.md"], repo) == []


@pytest.mark.parametrize("branch", ["main", "feature/x", "spec/search-api", "Spec/004-x", "fix/"])
def test_invalid_branch_names(repo, branch):
    assert violations(branch, [], repo)


def test_spec_branch_needs_its_spec_folder(repo):
    [problem] = violations("spec/005-other", [], repo)
    assert "specs/005-other/" in problem


def test_spec_branch_needs_all_spec_files(repo):
    (repo / "specs" / "004-search-api" / "plan.md").unlink()
    assert violations("spec/004-search-api", [], repo) == [
        "specs/004-search-api/plan.md is missing"
    ]


def test_spec_branch_with_unfinished_tasks_cannot_merge(repo):
    (repo / "specs" / "004-search-api" / "tasks.md").write_text("- [x] T001\n- [ ] T002 wire CLI\n")
    [problem] = violations("spec/004-search-api", [], repo)
    assert "T002 wire CLI" in problem


def test_docs_branch_cannot_change_code(repo):
    assert violations("docs/readme", ["README.md", "src/docling_pipeline/cli.py"], repo) == [
        "docs branch changes code: src/docling_pipeline/cli.py"
    ]


def test_existing_specs_satisfy_policy():
    """Every existing spec folder would pass as its own feature branch."""
    root = Path(__file__).parent.parent
    for spec_dir in sorted((root / "specs").glob("[0-9][0-9][0-9]-*")):
        assert violations(f"spec/{spec_dir.name}", []) == [], spec_dir.name
