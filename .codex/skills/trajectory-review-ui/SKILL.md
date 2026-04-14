---
name: trajectory-review-ui
description: Use this skill when implementing trajectory-aware previews, submission-summary views, case-review affordances, or file-type routing in skim.
---

# Trajectory Review UI

Use this skill for skim work that turns local review artifacts into specialized UI instead of generic file dumps.

## When To Use

Use this skill when:
1. Adding or changing trajectory-aware previews.
2. Adding submission-summary views for local review JSON.
3. Changing preview routing or file-type detection.
4. Adding case-review affordances inside preview panes.

Skip this skill when:
1. Work is generic Textual maintenance with no trajectory/submission behavior.
2. Changes are docs-only or purely stylistic.

## Product Rules

1. Keep the outer shell stable: directory tree on the left, preview panes on the right.
2. Prefer specialization inside a preview pane before introducing a new app mode or replacing the sidebar.
3. Treat local JSON as the source of truth.
4. Display URL fields when useful, but do not fetch them.
5. Preserve a safe fallback to the generic preview when detection or parsing fails.

## UI Defaults

1. For trajectories, prefer a step-list-plus-detail view.
2. Default to low-level event rows when the raw schema exposes them clearly.
3. Keep `final_output` prominent when present.
4. Keep metadata visible but subordinate to the main review flow.
5. Do not let specialized views break split-pane behavior.

## Code Shape

1. Keep routing, normalization, and rendering boundaries minimal and local.
2. Do not over-abstract early; add just enough structure to support one real schema cleanly.
3. Prefer small adapters over speculative multi-format frameworks.
4. Preserve the current small-codebase bias unless complexity clearly justifies a split.

## Test Expectations

1. Cover preview routing for generic files vs specialized JSON.
2. Cover normalization of the supported local trajectory schema.
3. Cover fallback behavior for malformed or partial JSON.
4. Cover pane interactions that specialized previews rely on.
5. Keep fixtures local and trimmed to the behavior under test.

## Output Expectations

When this skill is used, outputs should state:
1. Which local artifact shape is supported.
2. What specialized view was added or changed.
3. What fallback behavior remains in place.
4. Which tests prove the routing and review flow.
