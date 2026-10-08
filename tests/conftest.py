import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A small input tree: two supported docs, one nested doc, one unsupported file."""
    root = tmp_path / "input"
    (root / "nested").mkdir(parents=True)
    shutil.copy(FIXTURES / "report.html", root / "report.html")
    shutil.copy(FIXTURES / "notes.md", root / "notes.md")
    shutil.copy(FIXTURES / "notes.md", root / "nested" / "deep.md")
    (root / "malware.exe").write_bytes(b"MZ")
    return root
