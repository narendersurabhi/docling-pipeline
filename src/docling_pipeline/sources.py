"""Discover input documents from files, directories, and URLs."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".xhtml",
    ".md",
    ".csv",
    ".adoc",
    ".asciidoc",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}


@dataclass(frozen=True)
class Source:
    """A single document to process. `location` is a local path or an http(s) URL."""

    location: str
    name: str

    @property
    def is_url(self) -> bool:
        return _is_url(self.location)


def _is_url(value: str) -> bool:
    return urlparse(value).scheme in ("http", "https")


def _stem(location: str) -> str:
    if _is_url(location):
        path = PurePosixPath(urlparse(location).path)
        return path.stem or urlparse(location).netloc.replace(".", "_")
    return Path(location).stem


def discover(inputs: list[str], recursive: bool = True) -> list[Source]:
    """Expand inputs into a de-duplicated, sorted list of sources with unique output names."""
    locations: list[str] = []
    for raw in inputs:
        if _is_url(raw):
            locations.append(raw)
            continue
        path = Path(raw).expanduser()
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            locations.extend(
                str(p.resolve())
                for p in path.glob(pattern)
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
            )
        elif path.is_file():
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise ValueError(f"Unsupported file type: {path}")
            locations.append(str(path.resolve()))
        else:
            raise FileNotFoundError(f"Input not found: {raw}")

    locations = sorted(dict.fromkeys(locations))
    stems = Counter(_stem(loc) for loc in locations)
    sources = []
    for loc in locations:
        stem = _stem(loc)
        if stems[stem] > 1:
            stem = f"{stem}-{hashlib.sha1(loc.encode()).hexdigest()[:8]}"
        sources.append(Source(location=loc, name=stem))
    return sources
