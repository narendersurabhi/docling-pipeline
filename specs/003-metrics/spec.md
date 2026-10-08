# Spec 003: Metrics

| | |
|---|---|
| **Status** | Implemented |
| **Created** | 2026-10-08 |
| **Plan** | [plan.md](plan.md) · **Tasks** [tasks.md](tasks.md) |
| **Depends on** | [002-observability](../002-observability/spec.md) |

## Summary

Add OpenTelemetry **metrics** alongside the traces and logs from spec 002. The point is
aggregate answers that individual traces can't give cheaply: throughput, failure rate, latency
percentiles per stage and per format, and pages/chunks produced. Metrics link back to
traces through **exemplars**.

## Users and motivation

- **Operators** want dashboards and alerts such as "failure rate > 5%" or "p95 convert time
  for PDFs doubled", without querying every trace.
- **Capacity planning** needs pages and documents per second, and chunk-size distributions
  to tune `max_tokens`.

## Out of scope

Runtime/process metrics (CPU, memory, GC), GPU metrics, and dashboards-as-code.

---

## Functional requirements

### FR-016: Pipeline instruments
The pipeline records these instruments (meter `docling_pipeline`):

| Name | Kind | Unit | Attributes | Recorded |
|---|---|---|---|---|
| `pipeline.runs` | Counter | `{run}` | `outcome` | once per run: `completed`, or `aborted` if the run raised |
| `pipeline.run.duration` | Histogram | `s` | `outcome` | once per run |
| `pipeline.documents` | Counter | `{document}` | `doc.status`, `doc.format` | once per document, including skipped ones |
| `pipeline.document.duration` | Histogram | `s` | `doc.status`, `doc.format` | per processed document (not skipped) |
| `pipeline.stage.duration` | Histogram | `s` | `stage`, `outcome`, `doc.format` | per stage: `convert`, `export`, `chunk`. `outcome` is `ok` or `error` |
| `pipeline.pages` | Counter | `{page}` | `doc.format` | pages of each successful document |
| `pipeline.chunks` | Counter | `{chunk}` | `chunker.type` | chunks written |
| `pipeline.chunk.tokens` | Histogram | `{token}` | `chunker.type` | per chunk, only when the chunker has a tokenizer (hybrid) |
| `pipeline.errors` | Counter | `{error}` | `stage`, `error.type` | per failed document. `error.type` is the exception class name, or `ConversionFailed` when Docling reports failure without raising |

- `doc.format` is the lower-case file extension without the dot (`pdf`, `html`, …), taken
  from the URL path for URLs. It is only used when it's one of the supported extensions
  (FR-001); anything else is `unknown`. This keeps the label set bounded: a URL such as
  `/pdf/2408.09869` must not produce a `09869` label.
- Duration histograms use explicit bucket boundaries suited to seconds:
  `0.005 … 600`. Token histograms use `32 … 2048`.

### FR-017: Bounded attribute cardinality
Metric attributes may only use the keys `outcome`, `doc.status`, `doc.format`, `stage`,
`chunker.type`, `error.type`. Document names, sources, paths, and IDs are **never** metric
attributes. They belong on spans (FR-011).

### FR-018: Exemplars link metrics to traces
**Given** a sampled trace, **then** each `pipeline.document.duration` data point carries
exemplars whose `trace_id`/`span_id` identify the `document.process` span that recorded
them. `pipeline.stage.duration` exemplars identify the stage span (`document.convert`, etc.).

### FR-019: Metrics configuration and lifecycle
- `observability.metrics_exporter`: `none`, `console`, or `otlp`. Defaults to
  `$OTEL_METRICS_EXPORTER` or `none`. OTLP posts to `<otlp_endpoint>/v1/metrics`.
- `observability.metric_export_interval_s` (default `60`, > 0): periodic export interval.
- The CLI `--telemetry` flag sets the metrics exporter along with traces and logs.
- **Given** a run shorter than the export interval, **when** telemetry shuts down, **then**
  a final collection is exported, so short CLI runs never lose their metrics.
- Setup reuses an already-installed SDK `MeterProvider`, the same way as FR-015.
- `observability.enabled: false` disables metrics too.

## Non-functional requirements

NFR-004 (telemetry never breaks the pipeline) and NFR-005 (offline, in-memory-testable
telemetry) apply to metrics unchanged. The NFR-004 test runs with metrics exported to an
unreachable collector.
