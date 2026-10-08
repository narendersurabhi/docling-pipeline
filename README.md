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

Exit code is `0` if every document succeeded, `1` if any failed, and `2` on usage errors.

## Use as a library

```python
from docling_pipeline.config import PipelineConfig
from docling_pipeline.pipeline import DocumentPipeline

cfg = PipelineConfig(input_paths=["data/input"], output_dir="output")
summary = DocumentPipeline(cfg).run()
print(summary.counts)  # {'success': 12, 'failure': 1}
```

## Development: spec-driven

| Artifact | Purpose |
|---|---|
| [`specs/constitution.md`](specs/constitution.md) | Project principles every change is checked against |
| [`specs/001-document-pipeline/spec.md`](specs/001-document-pipeline/spec.md) | Requirements `FR-001`…`FR-010`, `NFR-001`…`NFR-003` with acceptance criteria |
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
