"""Orchestrates discover -> convert -> export -> chunk -> manifest."""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from docling.datamodel.base_models import ConversionStatus
from docling.document_converter import DocumentConverter

from docling_pipeline.chunking import build_chunker, write_chunks
from docling_pipeline.config import PipelineConfig
from docling_pipeline.converter import build_converter
from docling_pipeline.exporters import export_document
from docling_pipeline.sources import Source, discover

log = logging.getLogger(__name__)

META_FILE = "meta.json"
CHUNKS_FILE = "chunks.jsonl"
MANIFEST_FILE = "manifest.json"
_OK = {ConversionStatus.SUCCESS.value, ConversionStatus.PARTIAL_SUCCESS.value}


@dataclass
class DocumentResult:
    source: str
    name: str
    status: str
    output_dir: str
    files: dict[str, str] = field(default_factory=dict)
    num_pages: int = 0
    num_chunks: int = 0
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in _OK


@dataclass
class RunSummary:
    started_at: str
    finished_at: str
    output_dir: str
    results: list[DocumentResult]

    @property
    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "output_dir": self.output_dir,
            "counts": self.counts,
            "documents": [asdict(r) for r in self.results],
        }


class DocumentPipeline:
    def __init__(self, config: PipelineConfig, converter: DocumentConverter | None = None):
        self.config = config
        self._converter = converter
        self._chunker = None

    @property
    def converter(self) -> DocumentConverter:
        if self._converter is None:
            self._converter = build_converter(self.config.conversion)
        return self._converter

    @property
    def chunker(self):
        if self._chunker is None:
            self._chunker = build_chunker(self.config.chunking)
        return self._chunker

    def _already_done(self, out_dir: Path) -> DocumentResult | None:
        meta = out_dir / META_FILE
        if not (self.config.skip_existing and meta.exists()):
            return None
        data = json.loads(meta.read_text(encoding="utf-8"))
        return DocumentResult(**data) if data.get("status") in _OK else None

    def process(self, source: Source) -> DocumentResult:
        out_dir = Path(self.config.output_dir) / source.name
        if (done := self._already_done(out_dir)) is not None:
            done.status = ConversionStatus.SKIPPED.value
            return done

        result = DocumentResult(
            source=source.location,
            name=source.name,
            status=ConversionStatus.FAILURE.value,
            output_dir=str(out_dir),
        )
        conv = self.config.conversion
        start = time.perf_counter()
        try:
            res = self.converter.convert(
                source.location,
                raises_on_error=False,
                max_num_pages=conv.max_num_pages or sys.maxsize,
                max_file_size=int(conv.max_file_size_mb * 1024 * 1024)
                if conv.max_file_size_mb
                else sys.maxsize,
            )
            result.status = res.status.value
            result.errors = [e.error_message for e in res.errors]
            if result.ok:
                doc = res.document
                result.num_pages = doc.num_pages()
                result.files = export_document(doc, out_dir, self.config.exports)
                if self.config.chunking.enabled:
                    path = out_dir / CHUNKS_FILE
                    result.num_chunks = write_chunks(doc, self.chunker, source.location, path)
                    result.files["chunks"] = str(path)
        except Exception as exc:  # one bad document must not stop the batch (FR-006)
            if self.config.raise_on_error:
                raise
            log.exception("Failed to process %s", source.location)
            result.status = ConversionStatus.FAILURE.value
            result.errors.append(f"{type(exc).__name__}: {exc}")
        result.seconds = round(time.perf_counter() - start, 3)

        if result.status == ConversionStatus.FAILURE.value and self.config.raise_on_error:
            raise RuntimeError(f"Conversion failed for {source.location}: {result.errors}")

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / META_FILE).write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        return result

    def run(self, on_result: Callable[[DocumentResult], None] | None = None) -> RunSummary:
        started = datetime.now(UTC).isoformat()
        sources = discover(self.config.input_paths, recursive=self.config.recursive)
        log.info("Discovered %d document(s)", len(sources))

        results = []
        for source in sources:
            result = self.process(source)
            results.append(result)
            if on_result:
                on_result(result)

        summary = RunSummary(
            started_at=started,
            finished_at=datetime.now(UTC).isoformat(),
            output_dir=str(self.config.output_dir),
            results=results,
        )
        out = Path(self.config.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / MANIFEST_FILE).write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
        return summary
