# Spec 001: Document Pipeline

| | |
|---|---|
| **Status** | Implemented |
| **Created** | 2026-10-08 |
| **Plan** | [plan.md](plan.md) · **Tasks** [tasks.md](tasks.md) |

## Summary

A batch pipeline that turns heterogeneous documents (PDF, Office, HTML, Markdown, images, URLs)
into clean, structured outputs and retrieval-ready chunks, using
[Docling](https://github.com/docling-project/docling) for parsing and layout understanding.

## Users and motivation

- **RAG / search engineers** need consistent chunks with provenance (headings and pages) to embed.
- **Data engineers** need a repeatable batch job that survives bad files, can be re-run
  cheaply, and leaves an auditable record of what happened.

## Out of scope (for this spec)

Embedding generation, vector-store loading, a REST API, distributed execution. Each can
be a later spec that consumes this pipeline's `chunks.jsonl` output.

---

## Functional requirements

### FR-001: Discover input documents
The pipeline accepts a list of inputs, each a file, a directory, or an `http(s)` URL.

- **Given** a directory, **when** discovery runs with `recursive: true`, **then** every file
  with a supported extension in the tree is included. With `recursive: false`, only the top
  level is included.
- **Given** a directory containing unsupported files (e.g. `.exe`), **then** they are ignored.
- **Given** an explicit file path with an unsupported extension, **then** discovery raises an error.
- **Given** a path that does not exist, **then** discovery raises an error.
- **Given** the same file listed twice, **then** it is processed once.
- **Given** a URL, **then** it is passed through unchanged.

Supported extensions: `pdf docx pptx xlsx html htm xhtml md csv adoc asciidoc png jpg jpeg tif tiff bmp webp`.

### FR-002: Unique, deterministic output names
Each source gets an output folder named after its file stem.

- **Given** two sources with the same stem in different folders, **then** each gets the name
  `<stem>-<8 hex chars of sha1(location)>`. Names are identical across runs.
- **Given** a unique stem, **then** the folder name is exactly the stem.

### FR-003: Convert with Docling
Each source is converted to a `DoclingDocument` with Docling's `DocumentConverter`.

- PDF and image inputs use Docling's PDF pipeline. These settings are configurable: OCR on/off,
  table structure on/off, table mode (`accurate`/`fast`), picture image generation, image scale,
  thread count, accelerator device, per-document timeout, max pages, max file size.
- All other formats use Docling's default backends.

### FR-004: Export formats
- **Given** `exports` lists any of `markdown, json, html, text, doctags`, **when** a document
  converts successfully, **then** `<output_dir>/<name>/document.<ext>` is written for each
  (`md, json, html, txt, doctags`).
- The JSON export is a lossless `DoclingDocument` that can be loaded with
  `DoclingDocument.model_validate`.

### FR-005: Chunking
- **Given** `chunking.enabled: true`, **then** `<output_dir>/<name>/chunks.jsonl` holds one
  JSON object per line.
- `chunker: hybrid` uses Docling's token-aware `HybridChunker` with the configured tokenizer
  and `max_tokens`. `chunker: hierarchical` uses the structure-only `HierarchicalChunker`.
- Each record has: `id` (`<doc name>:<index>`), `source`, `chunk_index` (0-based,
  contiguous), `text`, `contextualized_text` (headings + text, meant for embedding),
  `headings`, `pages` (sorted unique page numbers, empty for non-paginated formats),
  `doc_item_refs`, `labels`. Hybrid chunks also carry `num_tokens`.
- **Given** `chunking.enabled: false`, **then** no chunks file is written.

### FR-006: Fault isolation
- **Given** a batch where one document fails, **when** `raise_on_error: false`, **then** every
  other document is still processed and the failure is recorded with `status: failure` and a
  non-empty `errors` list.
- **Given** `raise_on_error: true`, **then** the run stops with an exception at the first failure.

### FR-007: Per-document metadata and run manifest
- After each document, `<output_dir>/<name>/meta.json` records `source, name, status,
  output_dir, files, num_pages, num_chunks, seconds, errors`, plus `trace_id, span_id`
  *(amended by [spec 002 FR-013](../002-observability/spec.md#fr-013-correlation-ids-in-outputs))*.
- After the run, `<output_dir>/manifest.json` records `started_at`, `finished_at` (ISO-8601
  UTC), `output_dir`, `counts` per status, and a `documents` array.

### FR-008: Incremental re-runs
- **Given** `skip_existing: true` and a document whose `meta.json` has status `success` or
  `partial_success`, **then** it is not converted again and is reported as `skipped`.
- **Given** `skip_existing: true` and a previous `failure`, **then** the document is retried.

### FR-009: Configuration
- All settings load from a YAML file into a validated model. Missing keys take defaults.
- Invalid values (an unknown export format, `table_mode`, or `device`) are rejected with a
  validation error before any processing starts.

### FR-010: Command-line interface
- `docling-pipeline run [INPUTS...] [--config FILE] [options]` runs the pipeline. CLI flags
  override config values, and positional inputs replace `input_paths`.
- It prints one status line per document and a summary table.
- Exit code is `0` when no document failed and `1` when any document failed.
- Running with no inputs from either the CLI or the config is a usage error (exit code `2`).

## Non-functional requirements

### NFR-001: Reproducible, isolated environment
Python 3.11–3.13 in a uv-managed `.venv` with a uv-managed interpreter. `uv.lock` committed.

### NFR-002: Offline default test suite
`uv run pytest` passes with no network access and no ML model downloads. It uses HTML and
Markdown fixtures and the hierarchical chunker. Model-dependent tests are marked `slow`.

### NFR-003: Spec traceability
Every requirement ID in this spec is covered by at least one test tagged
`@pytest.mark.spec(...)`. This is enforced on every commit by the `spec-traceability` git hook
(originally hosted CI, moved to local hooks by constitution VIII).
