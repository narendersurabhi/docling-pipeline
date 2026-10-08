"""Write a DoclingDocument to disk in one or more formats."""

from __future__ import annotations

import json
from pathlib import Path

from docling_core.types.doc import DoclingDocument

from docling_pipeline.config import ExportFormat

_EXTENSIONS = {
    ExportFormat.MARKDOWN: "md",
    ExportFormat.JSON: "json",
    ExportFormat.HTML: "html",
    ExportFormat.TEXT: "txt",
    ExportFormat.DOCTAGS: "doctags",
}


def render(doc: DoclingDocument, fmt: ExportFormat) -> str:
    if fmt is ExportFormat.MARKDOWN:
        return doc.export_to_markdown()
    if fmt is ExportFormat.JSON:
        return json.dumps(doc.export_to_dict(), ensure_ascii=False)
    if fmt is ExportFormat.HTML:
        return doc.export_to_html()
    if fmt is ExportFormat.TEXT:
        return doc.export_to_text()
    if fmt is ExportFormat.DOCTAGS:
        return doc.export_to_doctags()
    raise ValueError(f"Unknown export format: {fmt}")


def export_document(
    doc: DoclingDocument, out_dir: Path, formats: list[ExportFormat]
) -> dict[str, str]:
    """Write each requested format to `out_dir/document.<ext>`; return {format: path}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for fmt in formats:
        path = out_dir / f"document.{_EXTENSIONS[fmt]}"
        path.write_text(render(doc, fmt), encoding="utf-8")
        written[fmt.value] = str(path)
    return written
