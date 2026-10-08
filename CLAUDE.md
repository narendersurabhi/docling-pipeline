# CLAUDE.md

This repo uses **spec-driven development**. Read `specs/constitution.md` and `specs/README.md`
before changing behaviour.

## Rules

- **Spec before code.** Any behaviour change starts with an edit to `specs/NNN-*/spec.md`:
  add a new `FR-###`/`NFR-###` (never reuse or renumber an ID) or amend acceptance
  criteria. New features get a new folder copied from `specs/_template/`.
- **Tests cite requirements.** Every test that verifies behaviour is decorated with
  `@pytest.mark.spec("FR-###", ...)`. Write the test before the implementation.
- **Keep `plan.md` and `tasks.md` in sync** with what you actually built. Tick tasks off as
  they land.
- **Default tests stay offline.** No model downloads or network. Anything needing
  models gets `@pytest.mark.slow`.

## Commands

```bash
uv sync                                   # uv-managed Python + locked deps in .venv
uv run pytest                             # fast suite + traceability gate
uv run pytest -m slow                     # model-dependent tests
uv run python scripts/spec_coverage.py    # requirement -> test matrix
uv run ruff check . && uv run ruff format --check .
```

## Layout

`src/docling_pipeline/`: `config` (FR-009), `sources` (FR-001/002), `converter` (FR-003),
`exporters` (FR-004), `chunking` (FR-005), `pipeline` (FR-006/007/008), `cli` (FR-010).
