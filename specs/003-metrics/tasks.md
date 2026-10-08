# Tasks 003: Metrics

Tasks are listed in order. Each one names the requirement IDs it satisfies.

## Spec
- [x] T001 Spec 003. Spec 002 out-of-scope note points here
- [x] T002 Amend FR-016 `doc.format` to the supported-extension allow-list (found by a test: `2408.09869` → `09869`)

## Tests first
- [x] T003 In-memory delta metric reader and `collect_metrics` fixture (NFR-005)
- [x] T004 Instrument tests: success, exception failure, reported failure, skipped, aborted, format label, hybrid tokens (FR-016)
- [x] T005 Attribute allow-list test over a mixed run (FR-017)
- [x] T006 Exemplar → span linkage test (FR-018)
- [x] T007 Exporter selection, env default, interval validation, flush on shutdown, reuse/disabled, CLI flag (FR-019)

## Implementation
- [x] T008 `ObservabilityConfig.metrics_exporter`, `metric_export_interval_s` (FR-019)
- [x] T009 `MeterProvider`, `build_metric_exporter`, `PipelineMetrics` instruments (FR-016, FR-019)
- [x] T010 `_stage()` span+duration helper. Document, run and chunk-token recording (FR-016, FR-018)
- [x] T011 `--telemetry` sets the metrics exporter (FR-019)

## Delivery
- [x] T012 End-to-end check against grafana/otel-lgtm: Tempo trace, Loki logs, Prometheus metrics and exemplars
- [x] T013 README, CLAUDE.md, example config
