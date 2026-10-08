import re
from pathlib import Path

import pytest

from docling_pipeline.sources import discover


@pytest.mark.spec("FR-001")
def test_directory_recursive_includes_supported_files_only(corpus: Path):
    names = sorted(Path(s.location).name for s in discover([str(corpus)], recursive=True))
    assert names == ["deep.md", "notes.md", "report.html"]


@pytest.mark.spec("FR-001")
def test_directory_non_recursive_is_top_level_only(corpus: Path):
    names = sorted(Path(s.location).name for s in discover([str(corpus)], recursive=False))
    assert names == ["notes.md", "report.html"]


@pytest.mark.spec("FR-001")
def test_unsupported_explicit_file_raises(corpus: Path):
    with pytest.raises(ValueError, match="Unsupported"):
        discover([str(corpus / "malware.exe")])


@pytest.mark.spec("FR-001")
def test_missing_path_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        discover([str(tmp_path / "nope.pdf")])


@pytest.mark.spec("FR-001")
def test_duplicates_are_processed_once(corpus: Path):
    f = str(corpus / "notes.md")
    assert len(discover([f, f, str(corpus / "." / "notes.md")])) == 1


@pytest.mark.spec("FR-001")
def test_urls_pass_through():
    url = "https://arxiv.org/pdf/2408.09869"
    [src] = discover([url])
    assert src.location == url
    assert src.is_url
    assert src.name == "2408"  # stem of the URL path's last segment


@pytest.mark.spec("FR-002")
def test_unique_stem_is_used_verbatim(corpus: Path):
    [src] = discover([str(corpus / "report.html")])
    assert src.name == "report"


@pytest.mark.spec("FR-002")
def test_colliding_stems_get_deterministic_hash_suffix(tmp_path: Path):
    for sub in ("a", "b"):
        (tmp_path / sub).mkdir()
        (tmp_path / sub / "doc.md").write_text("# hi\n")
    first = discover([str(tmp_path)])
    second = discover([str(tmp_path)])
    names = [s.name for s in first]
    assert len(set(names)) == 2
    assert all(re.fullmatch(r"doc-[0-9a-f]{8}", n) for n in names)
    assert names == [s.name for s in second]
