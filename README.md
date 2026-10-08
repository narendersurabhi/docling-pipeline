# docling-pipeline

A batch document-processing pipeline built on [Docling](https://github.com/docling-project/docling).
Point it at PDFs, Office files, HTML, Markdown, images, or URLs. It gives you clean Markdown/JSON
exports and retrieval-ready chunks with heading and page provenance, plus a manifest of what
happened.

The project is built with **spec-driven development**: see [`specs/`](specs/README.md).

```
inputs ─► discover ─► Docling convert ─► export (md/json/html/txt/doctags)
                                     └─► chunk (hybrid | hierarchical) ─► chunks.jsonl
                                     └─► meta.json      ...then manifest.json for the run
```

## Features

- **Many formats**: PDF, DOCX, PPTX, XLSX, HTML, Markdown, CSV, AsciiDoc, images, and URLs.
- **Configurable PDF understanding**: OCR, TableFormer (accurate/fast), picture extraction,
  CPU/MPS/CUDA acceleration, per-document timeouts and page/size limits.
- **RAG-ready chunks**: Docling's token-aware `HybridChunker` (or the structure-only
  `HierarchicalChunker`), emitted as flat JSONL with `contextualized_text`, headings, pages,
  and labels.
- **Built for batches**: one bad file doesn't kill the run, `skip_existing` makes re-runs
  incremental and retries only the failures, and `manifest.json` gives you an audit trail.
- **Observable from day one**: OpenTelemetry traces with a span per run, document and stage,
  logs correlated by `trace_id`/`span_id` (Docling's internal logs included), and metrics for
  throughput, latency and errors, with exemplars linking back to traces. Exports to the
  console or any OTLP backend.
- **Reproducible**: a uv-managed interpreter and a committed `uv.lock`.

## Quick start

Requires [uv](https://docs.astral.sh/uv/). uv installs the right Python into an isolated `.venv`.

```bash
git clone https://github.com/narendersurabhi/docling-pipeline.git
cd docling-pipeline
uv sync
```

Convert a folder, using the example config:

```bash
uv run docling-pipeline run data/input --config configs/pipeline.yaml
```

Or a single URL with flags only:

```bash
uv run docling-pipeline run https://arxiv.org/pdf/2408.09869 -o output -f markdown -f json --no-ocr
```

The first PDF run downloads Docling's layout and table models. To prefetch them (for example
in a Docker build or an air-gapped setup), run:

```bash
uv run docling-tools models download
```

## Output

```
output/
├── manifest.json                 # run timestamps, per-status counts, every document's result
└── <document-name>/
    ├── document.md               # one file per requested export format
    ├── document.json             # lossless DoclingDocument (reload with DoclingDocument.model_validate)
    ├── chunks.jsonl              # one chunk per line
    └── meta.json                 # status, timings, pages, chunk count, errors
```

A chunk record looks like this:

```json
{
  "id": "2408:5",
  "source": "https://arxiv.org/pdf/2408.09869",
  "chunk_index": 5,
  "text": "Two basic requirements to process PDF documents in our pipeline are ...",
  "contextualized_text": "3.1 PDF backends\nTwo basic requirements to process PDF documents ...",
  "headings": ["3.1 PDF backends"],
  "pages": [2, 3],
  "doc_item_refs": ["#/texts/27", "#/texts/28", "#/texts/30", "#/texts/46"],
  "labels": ["caption", "footnote", "text"],
  "num_tokens": 333
}
```

Embed `contextualized_text`, and keep `text`, `pages`, and `source` for citations.

## Configuration

All keys are optional. See [`configs/pipeline.yaml`](configs/pipeline.yaml) for every option
and its default. CLI flags override the config file:

| Flag | Effect |
|---|---|
| `INPUTS...` | Files, folders, or URLs (replaces `input_paths`) |
| `-c, --config` | YAML config file |
| `-o, --output` | Output directory |
| `-f, --format` | `markdown`, `json`, `html`, `text`, `doctags` (repeatable) |
| `--ocr/--no-ocr`, `--tables/--no-tables` | Toggle the OCR and table models |
| `--device` | `auto`, `cpu`, `mps`, `cuda`, `cuda:N`, `xpu` |
| `--chunk/--no-chunk`, `--chunker`, `--max-tokens` | Chunking controls |
| `--skip-existing` | Skip documents that already succeeded |
| `--telemetry` | `none`, `console`, `otlp` (traces, logs and metrics) |
| `--otlp-endpoint` | OTLP/HTTP base URL, e.g. `http://localhost:4318` |

Exit code is `0` if every document succeeded, `1` if any failed, and `2` on usage errors.

## Observability

Every run is one trace:

```
pipeline.run                       pipeline.documents.{total,succeeded,failed,skipped}
├── pipeline.discover              discover.sources
└── document.process   (per doc)   doc.name, doc.source, doc.status, doc.pages, doc.chunks
    ├── document.convert           docling.status   (ERROR + exception event on failure)
    ├── document.export            export.formats
    └── document.chunk             chunker.type, chunks.count
```

**Metrics** (Prometheus names after OTLP translation). Labels are low-cardinality only:
`doc_status`, `doc_format`, `stage`, `outcome`, `chunker_type`, `error_type`.

| Metric | What it tells you |
|---|---|
| `pipeline_documents_total` | throughput and failure rate by status and format |
| `pipeline_document_duration_seconds` | end-to-end latency per document (histogram) |
| `pipeline_stage_duration_seconds` | where the time goes: `convert` / `export` / `chunk` |
| `pipeline_errors_total` | failures by `stage` and `error_type` |
| `pipeline_pages_total`, `pipeline_chunks_total` | volume produced |
| `pipeline_chunk_tokens` | chunk-size distribution (hybrid chunker), for tuning `max_tokens` |
| `pipeline_runs_total`, `pipeline_run_duration_seconds` | runs by `outcome` (`completed` / `aborted`) |

For example:

```promql
sum(rate(pipeline_documents_total{doc_status="failure"}[5m])) / sum(rate(pipeline_documents_total[5m]))
histogram_quantile(0.95, sum by (le, doc_format) (rate(pipeline_stage_duration_seconds_bucket{stage="convert"}[5m])))
```

Duration histograms carry **exemplars** (`trace_id`/`span_id`), so a latency spike in
Grafana links straight to the trace of the slow document.

Every log line emitted inside a span carries that span's IDs, both on the console
(`… [trace_id=… span_id=…]`) and in the exported OpenTelemetry log record. `manifest.json`
records the run's `trace_id`, each `meta.json` records its document's `trace_id`/`span_id`, and
the CLI prints the `trace_id` at the end, so you can go from any output straight to its trace.

To view traces, logs and metrics locally (Grafana + Tempo + Loki + Prometheus in one
container):

```bash
docker compose -f docker-compose.observability.yml up -d
```

```bash
uv run docling-pipeline run data/input --telemetry otlp --otlp-endpoint http://localhost:4318
```

Then open http://localhost:3000 and go to **Explore**. Use **Tempo** to search traces by
`trace_id`, **Loki** with `{service_name="docling-pipeline"}` for logs, and **Prometheus**
for `pipeline_*` metrics.

To print spans and logs to the terminal without a backend, use `--telemetry console`. The
standard `OTEL_TRACES_EXPORTER`, `OTEL_LOGS_EXPORTER`, `OTEL_METRICS_EXPORTER`, and
`OTEL_EXPORTER_OTLP_ENDPOINT` env vars work too. See the `observability:` section of [`configs/pipeline.yaml`](configs/pipeline.yaml).
An unreachable collector never fails a run.

## Use as a library

```python
from docling_pipeline.config import PipelineConfig
from docling_pipeline.pipeline import DocumentPipeline

cfg = PipelineConfig(input_paths=["data/input"], output_dir="output")
summary = DocumentPipeline(cfg).run()
print(summary.counts, summary.trace_id)  # {'success': 12, 'failure': 1} 9ae8…
```

## Development: spec-driven

| Artifact | Purpose |
|---|---|
| [`specs/constitution.md`](specs/constitution.md) | Project principles every change is checked against |
| [`specs/001-document-pipeline/spec.md`](specs/001-document-pipeline/spec.md) | Pipeline requirements `FR-001`…`FR-010`, `NFR-001`…`NFR-003` |
| [`specs/002-observability/spec.md`](specs/002-observability/spec.md) | Tracing and logging requirements `FR-011`…`FR-015`, `NFR-004`…`NFR-005` |
| [`specs/003-metrics/spec.md`](specs/003-metrics/spec.md) | Metrics requirements `FR-016`…`FR-019` |
| [`plan.md`](specs/001-document-pipeline/plan.md) / [`tasks.md`](specs/001-document-pipeline/tasks.md) | Design and task breakdown, traced to requirement IDs |
| [`specs/_template/`](specs/_template) | Starting point for the next feature spec |

Tests declare which requirement they verify:

```python
@pytest.mark.spec("FR-006")
def test_one_failure_does_not_stop_batch(...): ...
```

`tests/test_spec_traceability.py` fails the build if any requirement has no test or if a test
cites an unknown ID. To see the matrix:

```bash
uv run python scripts/spec_coverage.py
```

Other commands:

```bash
uv run pytest              # fast, offline suite (no model downloads)
uv run pytest -m slow      # model-dependent tests (downloads a tokenizer)
uv run ruff check . && uv run ruff format --check .
```

## License

MIT
