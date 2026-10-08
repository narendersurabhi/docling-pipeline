# Tasks 001: Document Pipeline

Tasks are listed in order. Each one names the requirement IDs it satisfies.

## Setup
- [x] T001 Project scaffold: `pyproject.toml`, uv-managed interpreter, `uv.lock` (NFR-001)
- [x] T002 Register `spec` pytest marker and traceability gate (NFR-003)

## Tests first
- [x] T003 Discovery tests: dirs, recursion, filtering, errors, dedupe, URLs (FR-001)
- [x] T004 Output name collision tests (FR-002)
- [x] T005 Config tests: YAML load, defaults, validation errors (FR-009)
- [x] T006 Converter options mapping tests (FR-003)
- [x] T007 End-to-end HTML/Markdown pipeline tests: exports, chunks, meta, manifest (FR-004, FR-005, FR-007, NFR-002)
- [x] T008 Failure isolation tests with an injected failing converter (FR-006)
- [x] T009 Skip-existing / retry-failed tests (FR-008)
- [x] T010 CLI tests: overrides, exit codes, missing inputs (FR-010)

## Implementation
- [x] T011 `config.py` (FR-009)
- [x] T012 `sources.py` (FR-001, FR-002)
- [x] T013 `converter.py` (FR-003)
- [x] T014 `exporters.py` (FR-004)
- [x] T015 `chunking.py` (FR-005)
- [x] T016 `pipeline.py` (FR-006, FR-007, FR-008)
- [x] T017 `cli.py` (FR-010)

## Delivery
- [x] T018 CI workflow: ruff and pytest under uv (NFR-001, NFR-003)
- [x] T019 README and example config
