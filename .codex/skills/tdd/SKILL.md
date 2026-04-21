---
name: tdd
description: Use this skill when implementing or changing code in skim with a test-driven workflow. It enforces red-green-refactor with pytest and Textual tests first, then minimal code changes, then cleanup and linting.
---

# TDD Workflow

## Overview

Use this skill for feature work, bug fixes, and refactors that change behavior in skim.
Write a failing test first, implement the smallest change that passes, then refactor with tests still green.

## When To Use

Use this skill when:
1. Adding or changing behavior in `src/skim/`.
2. Fixing regressions or bugs.
3. Changing preview routing, file rendering, layout behavior, or input handling.
4. Refactoring logic with behavior-preservation requirements.

Skip this skill when:
1. Editing docs only.
2. Pure formatting/comment cleanup with no behavior changes.
3. One-off exploratory work where tests are intentionally deferred.

## Repository Defaults

1. Use Python 3.12+ and `uv`.
2. Put runtime code in `src/skim/`.
3. Put tests in `tests/` using `test_*.py`.
4. Run local verification in this order:
   - `uv run ruff format .`
   - `uv run ruff check .`
   - `uv run pytest -v`
5. Use deterministic, local-only tests. Do not rely on network or remote artifacts.
6. For Textual behavior, prefer app-level tests that exercise routing, pane state, and key interactions.
7. If async Textual tests fail because the pytest async harness is incomplete, repair the harness first and then continue the red-green loop.

## Workflow (Red -> Green -> Refactor)

### 1. Red: Specify Behavior First

1. Identify the smallest externally visible behavior change.
2. Write or update one failing test that captures only that behavior.
3. Confirm failure explicitly:
   - `uv run pytest tests/<target_test_file>.py -k <test_name>`
4. If the test does not fail for the expected reason, fix the test before code changes.
5. When working on Textual UI behavior, assert outcomes the user can observe: selected view kind, pane state, rendered section presence, or navigation result.

### 2. Green: Implement Minimal Change

1. Implement only what is needed to make the failing test pass.
2. Re-run the focused test first.
3. Then run adjacent tests likely impacted.
4. Avoid broad refactors in this phase.

### 3. Refactor: Improve Without Behavior Drift

1. Refactor naming/structure only after tests are green.
2. Keep changes small and re-run tests frequently.
3. Before final verification, apply repo-wide formatting:
   - `uv run ruff format .`
4. Re-run full suite for confidence:
   - `uv run pytest -v`
5. Ensure lint still passes:
   - `uv run ruff check .`

## Test Scope Rules

1. Start with the narrowest failing unit test.
2. Add integration-style tests only when behavior crosses module boundaries.
3. Do not overfit tests to internal implementation details.
4. Prefer explicit fixtures/test data over hidden globals.
5. For JSON-driven features, keep sample data small and local to the repo or test fixture.

## Change Checklist

Before finishing:
1. At least one failing test was observed before implementation.
2. New/updated behavior is covered by tests.
3. Ruff formatting has been applied with `uv run ruff format .`.
4. Ruff check passes.
5. All relevant tests pass.
6. Notes include what behavior changed and why.

## Common Commands

1. Run one test file:
   - `uv run pytest tests/test_<name>.py`
2. Run one test:
   - `uv run pytest tests/test_<name>.py -k <test_case>`
3. Format the repo:
   - `uv run ruff format .`
4. Run all tests:
   - `uv run pytest -v`
5. Lint:
   - `uv run ruff check .`
6. Run the app in dev mode when manual UI checking is needed:
   - `uv run skim-dev`

## Output Expectations

When this skill is used, outputs should include:
1. The failing test that drove the change.
2. The minimal implementation change summary.
3. Evidence that formatting, tests, and lint pass (or explicit blockers).
