# AGENTS

skim is a small Textual TUI file browser that is evolving into a local review tool for agent trajectories and related case artifacts.

## Product defaults

- Preserve the existing browser shell: directory tree on the left, preview panes on the right.
- Prefer specialization inside preview panes before changing the outer layout.
- Treat local files as the source of truth. Do not fetch URLs or use third-party services/tools to inspect JSON-linked artifacts.
- Keep the codebase small on purpose. The single app module is the default; split only when the change clearly earns it.

## Engineering defaults

- Use `uv` for repo commands.
- Treat `uv run ruff format .` as part of normal local verification, not an optional cleanup step.
- Keep tests focused on the changed behavior. If async Textual tests are broken, fix the test harness before leaning on TDD.
- Prefer small, readable changes over broad refactors.
- Do not change unrelated files or undo user work.

## Workflow defaults

- Implement in tight slices and verify the touched area first.
- After each code edit batch, and before commit or push, run local verification in this order:
  `uv run ruff format .`
  `uv run ruff check .`
  `uv run pytest -v`
- After a green, reviewable slice, commit by default unless the user says not to.
- Apply the same format/lint/test sequence before pushing updates to an already open PR; CI checks formatting independently of lint.
- Never bundle unrelated changes into the same commit.
- Keep git usage non-interactive and conservative in dirty worktrees.
