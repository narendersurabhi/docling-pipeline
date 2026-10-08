# Plan 003: Metrics

Implements [spec.md](spec.md). Extends [plan 002](../002-observability/plan.md).

## Architecture

```
setup_telemetry ─► MeterProvider(resource, exemplar_filter=trace_based (SDK default))
                     └─ PeriodicExportingMetricReader(interval) ─► console | OTLP/HTTP /v1/metrics | none
observability.instruments (PipelineMetrics on the global proxy meter)
pipeline.run()                 ─► runs, run.duration                        (inside pipeline.run span)
pipeline.process()             ─► documents, document.duration, pages,      (inside document.process span)
                                  chunks, errors
pipeline._stage(name)          ─► stage.duration                            (inside document.<stage> span)
chunking.write_chunks(on_chunk)─► chunk.tokens
Telemetry.shutdown()           ─► MeterProvider.shutdown() → final collect + export
```

## Key decisions

- **Instruments live on the global proxy meter.** They're created at import time and bind
  to whichever `MeterProvider` is installed later, the same pattern as `tracer`.
- **One `_stage()` context manager** creates the stage span *and* records its duration.
  This guarantees span and metric stay in sync, and that the histogram is recorded while
  the stage span is current, which is what makes exemplars point at it (FR-018).
- **Exemplars use the SDK default `trace_based` filter.** Only sampled traces produce
  exemplars, so `sample_ratio` controls exemplar volume too.
- **Cardinality is bounded by construction** (FR-017). `doc.format` comes from a fixed
  extension allow-list, statuses and stages are enums, and `error.type` is an exception
  class name. A test asserts the key allow-list over a run with failures and skips.
- **Explicit histogram buckets via `explicit_bucket_boundaries_advisory`.** The SDK default
  buckets are millisecond-oriented (0–10 000) and useless for second-valued durations.
- **The run is recorded even when it aborts** (`try/finally` with `outcome=aborted`), so
  crash loops are visible in `pipeline_runs_total{outcome="aborted"}`.
- **`shutdown_on_exit=False` on the MeterProvider.** `Telemetry.shutdown()` is the single
  owner of the lifecycle, so there's no double export at interpreter exit.

## Prometheus names (via OTLP → Prometheus translation)

`pipeline_runs_total`, `pipeline_run_duration_seconds_*`, `pipeline_documents_total`,
`pipeline_document_duration_seconds_*`, `pipeline_stage_duration_seconds_*`,
`pipeline_pages_total`, `pipeline_chunks_total`, `pipeline_chunk_tokens_*`,
`pipeline_errors_total`. Attribute dots become underscores (`doc_format`).

## Test strategy

- The session fixture adds an `InMemoryMetricReader` with **delta** temporality.
  `collect_metrics()` returns only what was recorded since the previous call.
- Exemplar test: compare exemplar `span_id`s to the in-memory exported spans.
- Short-run flush: a collecting exporter behind a 1-hour periodic reader must still receive
  data at `Telemetry.shutdown()`.

## Known limitation (follow-up)

`doc.format` comes from the extension, so URLs without one (for example arXiv
`/pdf/2408.09869`) are `unknown`. A later spec could use Docling's detected `InputFormat`
(also a bounded enum) once conversion has started.
