---
name: commit-discipline
description: Use this skill when doing code-changing work in this repository that should end with a small, reviewable commit, especially after a green TDD slice or completed ticket slice.
---

# Commit Discipline

Use this skill after implementation or review work in this repo when changes are ready to commit.

## Purpose

Follow the repo default in `AGENTS.md`: after a green, reviewable slice, commit by default unless the user says not to.

## When To Use

Use this skill when:
1. A behavior-changing ticket slice is green.
2. A review fix is complete and verified.
3. A coherent docs+code slice is ready and reviewable.

Do not use this skill when:
1. Work is still in a red or unstable state.
2. The user explicitly says not to commit yet.
3. The task is planning-only or pure exploration.
4. The worktree contains unrelated user changes that cannot be safely separated.

## Workflow

1. Confirm scope.
   - Commit only the active ticket or review slice.
   - Do not bundle unrelated files.
2. Verify readiness.
   - Run `uv run ruff format .` before lint, tests, commit, or push.
   - Run the touched-area tests first.
   - Run broader required checks only when the slice warrants it.
   - At minimum, finish with:
     `uv run ruff format .`
     `uv run ruff check .`
     `uv run pytest -v`
   - Apply the same sequence before pushing more commits to an already open PR.
   - Do not commit with known red-phase failures in the slice.
3. Review the diff.
   - Inspect `git status --short`.
   - Inspect `git diff --stat` and a narrow diff.
   - Confirm the commit is small and reviewable.
4. Commit by default.
   - Commit after each coherent green slice.
   - Prefer multiple small commits over one large commit.
5. Report clearly.
   - State the commit created and what slice it covers.
   - If no commit was made, state the blocker.

## Commit Rules

1. Default unit of commit: one green, reviewable ticket slice.
2. Preferred timing: after focused tests are green and before starting the next sub-slice.
3. Hold the commit only when:
   - the user asked to wait
   - unrelated worktree changes make the commit unsafe
   - the slice is still red or unstable
4. Never amend or rewrite history unless explicitly requested.
5. Never include unrelated user changes.
6. Avoid interactive git flows.

## Commit Messages

Rules:
1. Keep the subject short and factual.
2. Use imperative/lowercase style unless the repo already uses another clear convention.
3. Include a ticket id only when one is already part of the task context.
4. Do not invent issue prefixes or project codes.

## Relationship To Other Skills

1. Use `tdd` for behavior-changing work.
2. Use this skill after the slice is green to handle commit follow-through.
