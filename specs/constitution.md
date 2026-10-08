# Project Constitution

These principles govern every change to `docling-pipeline`. Specs, plans, and code reviews
check against them.

## I. Spec first
Behaviour is defined in `specs/NNN-feature/spec.md` **before** it is implemented. A pull
request that changes behaviour updates the spec in the same PR. If code and spec disagree,
the spec is the source of truth and the code is the bug.

## II. Every requirement is testable and tested
Each requirement has a stable ID (`FR-###` functional, `NFR-###` non-functional) and
acceptance criteria written as Given / When / Then. Every ID is referenced by at least one
test via `@pytest.mark.spec("FR-###")`. `tests/test_spec_traceability.py` enforces this in CI,
and also rejects tests that cite IDs that don't exist.

## III. Requirement IDs are permanent
IDs are never renumbered or reused. A dropped requirement is marked
`~~FR-###~~ (withdrawn: reason)` and stays in the spec.

## IV. Fault isolation over fail-fast
A batch pipeline must keep going when one document is bad. Failures are recorded, never
swallowed silently.

## V. Reproducible environment
The project runs in a uv-managed virtual environment with a uv-managed interpreter
(`python-preference = "only-managed"`). `uv.lock` is committed.

## VI. Observable from day one
Every unit of work emits OpenTelemetry traces with a span per meaningful stage, logs
correlated with those spans (`trace_id`/`span_id`), and low-cardinality metrics (counts,
durations, errors) linked to traces through exemplars. New features extend the span tree and
the logs in the same PR that adds the behaviour, and tests assert on the emitted telemetry.
Telemetry failures must never break the pipeline.

## VII. Fast, offline tests
The default test suite must not download ML models or reach the network. Tests that need
models are marked `slow` and are opt-in.
