"""Split converted documents into retrieval-ready chunks with provenance metadata."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from docling_core.transforms.chunker import BaseChunker, HierarchicalChunker
from docling_core.types.doc import DoclingDocument

from docling_pipeline.config import ChunkerType, ChunkingConfig


def build_chunker(cfg: ChunkingConfig) -> BaseChunker:
    if cfg.chunker is ChunkerType.HIERARCHICAL:
        return HierarchicalChunker()

    # Imported lazily: the hybrid chunker pulls in transformers and downloads a tokenizer.
    from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

    tokenizer = HuggingFaceTokenizer.from_pretrained(
        model_name=cfg.tokenizer, max_tokens=cfg.max_tokens
    )
    return HybridChunker(tokenizer=tokenizer, merge_peers=cfg.merge_peers)


def iter_chunks(
    doc: DoclingDocument, chunker: BaseChunker, source: str
) -> Iterator[dict[str, Any]]:
    """Yield one JSON-serialisable record per chunk.

    `text` is the raw chunk text; `contextualized_text` prepends the heading path and is
    what you usually want to embed.
    """
    tokenizer = getattr(chunker, "tokenizer", None)
    for i, chunk in enumerate(chunker.chunk(dl_doc=doc)):
        contextualized = chunker.contextualize(chunk)
        pages = sorted({prov.page_no for item in chunk.meta.doc_items for prov in item.prov})
        record: dict[str, Any] = {
            "id": f"{doc.name}:{i}",
            "source": source,
            "chunk_index": i,
            "text": chunk.text,
            "contextualized_text": contextualized,
            "headings": chunk.meta.headings or [],
            "pages": pages,
            "doc_item_refs": [item.self_ref for item in chunk.meta.doc_items],
            "labels": sorted({str(item.label.value) for item in chunk.meta.doc_items}),
        }
        if tokenizer is not None:
            record["num_tokens"] = tokenizer.count_tokens(contextualized)
        yield record


def write_chunks(
    doc: DoclingDocument,
    chunker: BaseChunker,
    source: str,
    path: Path,
    on_chunk: Callable[[dict[str, Any]], None] | None = None,
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for record in iter_chunks(doc, chunker, source):
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
            if on_chunk:
                on_chunk(record)
    return count
