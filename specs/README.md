# Specs

This project uses **spec-driven development** (SDD). Specs are not after-the-fact documentation.
They are the contract that code and tests are written against.

```
specs/
├── constitution.md              # non-negotiable project principles
└── NNN-feature-name/
    ├── spec.md                  # WHAT and WHY: requirements + acceptance criteria (IDs)
    ├── plan.md                  # HOW: architecture, modules, data contracts
    └── tasks.md                 # ordered, checkable work items, each tied to requirement IDs
```

## Workflow

1. **Specify.** Copy `_template/` to `specs/NNN-short-name/` and write `spec.md`. Give each
   requirement a new `FR-###` / `NFR-###` ID and Given/When/Then acceptance criteria.
   Use **[NEEDS CLARIFICATION: …]** for anything unresolved. A spec isn't ready while any remain.
2. **Plan.** Write `plan.md`: which modules change, data contracts, trade-offs. Check it
   against `constitution.md`.
3. **Task.** Break the plan into `tasks.md`. Each task lists the requirement IDs it satisfies.
4. **Test first.** Write failing tests tagged `@pytest.mark.spec("FR-###")`.
5. **Implement** until the tests pass, then tick the tasks off.
6. **Verify.** `uv run pytest` runs the traceability check, which fails if any requirement
   has no test or a test cites an unknown ID.

Changing behaviour later? Edit the spec first (new ID, or amend the acceptance criteria of
an existing one), then follow steps 2–6.

## Useful commands

```bash
uv run pytest                            # tests + spec traceability gate
uv run python scripts/spec_coverage.py   # requirement -> tests matrix
```
