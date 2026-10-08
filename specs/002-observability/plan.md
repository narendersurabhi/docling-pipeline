# Plan 002: Observability

Implements [spec.md](spec.md). Checked against [constitution](../constitution.md).

## Architecture

```
cli.run ──► setup_telemetry(cfg.observability)
              ├─ TracerProvider (Resource, ParentBased(TraceIdRatio)) ─► Batch/SimpleSpanProcessor ─► console | OTLP/HTTP | none
              ├─ LoggerProvider (Resource) ─────────────────────────────► Batch/SimpleLogRecordProcessor ─► console | OTLP/HTTP | none
              └─ root logger handlers
                   ├─ console (Rich) with TraceContextFormatter  → "… [trace_id=… span_id=…]"
                   └─ OTel LoggingHandler (opentelemetry-instrumentation-logging) → LoggerProvider
          ──► DocumentPipeline.run   (spans via module-level `tracer`)
          ──► Telemetry.shutdown()   (finally: flush/shutdown, remove handlers)
```

Because the OTel `LoggingHandler` sits on the **root** logger, Docling's own internal logs
are exported too, and they're correlated with the `document.convert` span they ran in.

## Modules

| Module | Change | Requirements |
|---|---|---|
| `config.py` | `ObservabilityConfig`, `TelemetryExporter`, env-var defaults | FR-014 |
| `observability.py` | `build_resource`, `build_span_exporter`, `build_log_exporter`, `build_providers`, `setup_telemetry`, `Telemetry.shutdown`, `TraceContextFormatter`, `current_ids` | FR-012, FR-014, FR-015, NFR-004 |
| `pipeline.py` | Spans `pipeline.run`, `pipeline.discover`, `document.process`, `document.{convert,export,chunk}`. Outcome logs. `trace_id`/`span_id` on `DocumentResult` and `RunSummary` | FR-011, FR-012, FR-013 |
| `cli.py` | `--telemetry`, `--otlp-endpoint`, setup/try/finally shutdown, print `trace_id` | FR-013, FR-014, FR-015 |
| `docker-compose.observability.yml` | `grafana/otel-lgtm` (Collector + Tempo + Loki + Grafana) | — |

## Key decisions

- **OTLP over HTTP/protobuf, not gRPC.** The wheel is smaller, there's no grpcio build
  dependency, and every major backend supports it.
- **Global providers are installed once and reused.** OpenTelemetry forbids replacing the
  global providers. `setup_telemetry` detects existing SDK providers and attaches to them
  (`owns_providers=False`), so host applications and the test harness keep control.
- **The console formatter reads the active span at format time** rather than patching the
  global `LogRecordFactory` (as `LoggingInstrumentor` does). That keeps setup side-effect
  free and reversible.
- **Failures are visible in three places:** span status `ERROR` with an exception event, an
  `ERROR` log with the stack trace (correlated), and `meta.json` with `trace_id`/`span_id`.
  Any one of them leads you to the other two.
- **Default exporters are `none`.** IDs are still generated and written to outputs, so
  turning exporting on later still lets you correlate outputs. The standard `OTEL_*` env vars
  switch it on without config changes.
- **No metrics yet** (out of scope). The span attributes `doc.pages`, `doc.chunks` and the
  durations can derive RED metrics in the backend (for example Tempo's metrics-generator).

## Test strategy (NFR-005)

- A session-scoped fixture installs global providers with `InMemorySpanExporter` and
  `InMemoryLogRecordExporter` using simple (synchronous) processors. The `spans`/`logs`
  fixtures clear them per test.
- Lifecycle tests build non-global providers or stub `setup_telemetry` in the CLI.
- NFR-004 runs the real CLI in a subprocess against `http://127.0.0.1:9` (nothing listens
  there), so it exercises the owned-provider path end to end, offline.
