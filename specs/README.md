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

0. **Branch.** `git switch -c spec/NNN-short-name main`. One feature per branch, with the
   branch name matching the spec folder (constitution VIII).
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
7. **Pull request.** Push the branch and open a PR into `main` (the template has a checklist).
   CI runs lint, the traceability gate, the tests on Python 3.11–3.13, and `branch-policy`.
   Merge only when everything is green. `main` rejects direct pushes.

Suggested commit sequence on a feature branch, so the SDD order shows in history:
`spec: …` (spec/plan/tasks) → `test: …` (failing tests) → `feat: …` (implementation and docs).

| Branch | For | Policy |
|---|---|---|
| `spec/NNN-short-name` | a feature from `specs/NNN-short-name/` | spec, plan and tasks must exist; all tasks ticked |
| `fix/<name>` | a bug fix | cite the violated requirement ID in the PR |
| `chore/<name>` | CI, tooling, dependencies, refactors | no behaviour change |
| `docs/<name>` | documentation only | may not touch `src/` or `tests/` |

Changing behaviour later? Edit the spec first (new ID, or amend the acceptance criteria of
an existing one), then follow steps 2–6.

## Useful commands

```bash
uv run pytest                            # tests + spec traceability gate
uv run python scripts/spec_coverage.py   # requirement -> tests matrix
```
