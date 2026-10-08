# Tasks 002: Observability

Tasks are listed in order. Each one names the requirement IDs it satisfies.

## Spec and governance
- [x] T001 Constitution principle VI "Observable from day one". Templates require an Observability section
- [x] T002 Amend FR-007 (`meta.json` gains `trace_id`/`span_id`) (FR-013)

## Tests first
- [x] T003 Session-wide in-memory span/log exporters in `conftest.py` (NFR-005)
- [x] T004 Span tree, failure status, skipped docs, chunking-off tests (FR-011)
- [x] T005 Log correlation, error logs with exception, console format tests (FR-012)
- [x] T006 Manifest/meta/CLI trace ID tests (FR-013)
- [x] T007 Exporter selection, env defaults, resource, validation, sampling, disabled, CLI flags (FR-014)
- [x] T008 Reuse vs. owned providers, shutdown on failure and exception (FR-015)
- [x] T009 Unreachable OTLP collector subprocess test (NFR-004)

## Implementation
- [x] T010 `ObservabilityConfig` (FR-014)
- [x] T011 `observability.py` providers, exporters, handlers, lifecycle (FR-012, FR-014, FR-015)
- [x] T012 Instrument `pipeline.py` with spans, logs and IDs (FR-011, FR-012, FR-013)
- [x] T013 CLI flags, try/finally shutdown, print trace ID (FR-013, FR-014, FR-015)

## Delivery
- [x] T014 `docker-compose.observability.yml` (grafana/otel-lgtm) and example config section
- [x] T015 README "Observability" section and CLAUDE.md rule
