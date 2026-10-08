# Spec 002: Observability (traces, spans, logs)

| | |
|---|---|
| **Status** | Implemented |
| **Created** | 2026-10-08 |
| **Plan** | [plan.md](plan.md) · **Tasks** [tasks.md](tasks.md) |
| **Depends on** | [001-document-pipeline](../001-document-pipeline/spec.md) |

## Summary

Instrument the pipeline with [OpenTelemetry](https://opentelemetry.io/) so every run can be
inspected after the fact: a trace per run, a span per document and per stage, and structured
logs tied to those spans. Telemetry is exported to the console or any OTLP backend.

## Users and motivation

- **Operators** need to know which document failed, which stage it failed in, and how long each stage took,
  without re-running anything.
- **Developers** need to jump from a log line to the trace that produced it, and from a
  `manifest.json` entry to its trace in the backend.

## Out of scope

Metrics (counters and histograms), HTTP client auto-instrumentation, and profiling. Candidates
for a later spec.

---

## Functional requirements

### FR-011: Span hierarchy for every run
Each pipeline run produces exactly one trace with this shape:

```
pipeline.run
├── pipeline.discover
└── document.process            (one per source)
    ├── document.convert
    ├── document.export
    └── document.chunk          (only when chunking is enabled)
```

- `pipeline.run` attributes: `pipeline.inputs`, `pipeline.output_dir`, `pipeline.exports`,
  `pipeline.chunker`. Set on completion: `pipeline.documents.total`, `.succeeded`, `.failed`,
  `.skipped`.
- `pipeline.discover` attributes: `discover.sources`.
- `document.process` attributes: `doc.name`, `doc.source`, `doc.is_url`, and on completion
  `doc.status`, `doc.pages`, `doc.chunks`.
- `document.convert` attributes: `docling.status`, `doc.pages`. `document.export`:
  `export.formats`. `document.chunk`: `chunker.type`, `chunks.count`.
- **Given** a document fails, **then** its `document.process` span has status `ERROR`, and
  the exception is recorded as a span event when there is one. Sibling documents' spans keep
  status unset or OK.
- **Given** a document is skipped (FR-008), **then** its `document.process` span has
  `doc.status = skipped` and no child stage spans.

### FR-012: Logs correlated with traces
- The pipeline emits structured log records through stdlib `logging` at least for: run
  start, each document's outcome (`INFO` on success or skip, `ERROR` on failure, with
  exception info), and run end.
- Each record emitted inside a span carries that span's `trace_id` and `span_id`, both in the
  OpenTelemetry log record and in the console log line (`trace_id=<32 hex> span_id=<16 hex>`).
- Document outcome records carry the attributes `doc.name` and `doc.status`.
- Records go to the configured log exporter in addition to the console.

### FR-013: Correlation IDs in outputs
- `manifest.json` includes `trace_id`, the 32-hex trace ID of the run.
- Each `meta.json` includes `trace_id` and `span_id` (16 hex) of its `document.process` span.
- The CLI prints the run's `trace_id` after the summary table.

### FR-014: Telemetry configuration
A new `observability` section in the pipeline config:

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | `false` turns all telemetry into no-ops. Console logging still works. |
| `service_name` | `docling-pipeline` | Resource `service.name` |
| `environment` | `dev` | Resource `deployment.environment.name` |
| `traces_exporter` | `$OTEL_TRACES_EXPORTER` or `none` | `none`, `console`, or `otlp` |
| `logs_exporter` | `$OTEL_LOGS_EXPORTER` or `none` | `none`, `console`, or `otlp` |
| `otlp_endpoint` | `null` (exporter falls back to `$OTEL_EXPORTER_OTLP_ENDPOINT`) | OTLP/HTTP base URL, e.g. `http://localhost:4318`. `/v1/traces` and `/v1/logs` are appended. |
| `otlp_timeout_s` | `10` | Export timeout |
| `sample_ratio` | `1.0` | Parent-based trace ID ratio sampling, in [0, 1] |
| `log_level` | `INFO` | Minimum level exported through OpenTelemetry |

- The resource also carries `service.version` (the package version).
- Invalid exporter names and out-of-range `sample_ratio` are rejected at config load.
- The CLI exposes `--telemetry [none|console|otlp]` (sets both exporters) and `--otlp-endpoint`.

### FR-015: Telemetry lifecycle
- The CLI sets up telemetry before processing and flushes and shuts it down on exit. This
  includes runs that end in a document failure (exit code 1) or an exception.
- Shutdown removes the logging handlers that setup installed.
- If telemetry providers are already configured in the process (for example by a host
  application or a test harness), setup reuses them instead of replacing them, and shutdown
  only flushes them.

## Non-functional requirements

### NFR-004: Telemetry never breaks the pipeline
**Given** an unreachable OTLP endpoint, **when** the pipeline runs, **then** every document is
processed with the same results as with telemetry disabled. Shutdown completes within
`otlp_timeout_s` plus a small margin, and no exception propagates.

### NFR-005: Telemetry is testable offline
Tests assert on spans and log records through in-memory exporters. No collector is required.
