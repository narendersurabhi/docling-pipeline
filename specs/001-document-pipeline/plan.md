# Plan 001: Document Pipeline

Implements [spec.md](spec.md). Checked against [constitution](../constitution.md).

## Architecture

```
inputs ──► sources.discover ──► DocumentPipeline.process (per source)
                                   │
                                   ├─ converter.build_converter ─► Docling DocumentConverter.convert
                                   ├─ exporters.export_document ─► document.{md,json,html,txt,doctags}
                                   ├─ chunking.write_chunks ─────► chunks.jsonl
                                   └─ meta.json
                                 ► manifest.json (after all sources)
```

## Modules

| Module | Responsibility | Requirements |
|---|---|---|
| `config.py` | Pydantic models `PipelineConfig`, `ConversionConfig`, `ChunkingConfig`, YAML loader | FR-009 |
| `sources.py` | `discover()` expands files, dirs and URLs into `Source(location, name)` | FR-001, FR-002 |
| `converter.py` | Maps `ConversionConfig` to `PdfPipelineOptions`, builds `DocumentConverter` | FR-003 |
| `exporters.py` | `render()` / `export_document()` per `ExportFormat` | FR-004 |
| `chunking.py` | `build_chunker()`, `iter_chunks()`, `write_chunks()` | FR-005 |
| `pipeline.py` | `DocumentPipeline.process/run`, `DocumentResult`, `RunSummary` | FR-006, FR-007, FR-008 |
| `cli.py` | Typer app; merges CLI flags over YAML config | FR-010 |
| `observability.py` | OpenTelemetry setup (see [plan 002](../002-observability/plan.md)) | FR-011–FR-015 |

## Key decisions

- **One `convert()` call per document**, not `convert_all()`. This gives exact per-document
  timing and error attribution, and makes skip logic simple. Docling's batch concurrency
  defaults to 1, so no throughput is lost.
- **Lazy model loading.** The converter and the hybrid chunker are built on first use, so
  runs that are fully skipped, and the HTML/Markdown tests, never load models (NFR-002).
- **The converter can be injected** into `DocumentPipeline(config, converter=...)` so tests
  can simulate failures (FR-006) without corrupt fixtures.
- **`meta.json` is the incremental-run checkpoint** (FR-008). It's written after outputs, so
  a crash mid-document leaves no success marker and the document is retried.
- **Chunk records are flat JSON.** Embedders and vector DBs ingest them directly without
  needing the docling-core types.

## Traceability mechanism (NFR-003)

- Register a pytest marker `spec(*ids)` in `pyproject.toml`.
- `scripts/spec_coverage.py` parses requirement IDs from `specs/*/spec.md` headings
  (`### FR-001: ...`) and finds marker usages in `tests/` by AST, then prints a matrix.
- `tests/test_spec_traceability.py` runs the same logic and fails on uncovered or unknown IDs.

## Risks

- Docling's API moves quickly. The minimum version is pinned in `pyproject.toml`, the exact
  version in `uv.lock`, and the pre-push test suite exercises the real library (no mocks for
  HTML/Markdown paths).
- The first PDF run downloads layout/table/OCR models (~hundreds of MB). The README documents
  prefetching with `docling-tools models download`.
