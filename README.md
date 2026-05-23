# skim

<img src="./docs/assets/skim-retro-reviewer.png" alt="SKIM retro reviewer icon" width="96">

**A local review layer for agent trace, evaluation artifacts and messy workspaces.**

SKIM helps inspect traces, trajectories, tool-call logs, model outputs, prompts,
eval artifacts, generated folders, and other local files produced during agent
system development or evaluation.

Annotations can be attached to review targets: whole files, directories, or
structured nodes inside JSON. The same review state can then be inspected from
the CLI, TUI, or Web UI.

When an agent run gets messy, SKIM lets the review leave evidence behind.

## The loop

Start in interactive mode: open a local workspace in the TUI or Web UI. Inspect
the artifacts, e.g., tool calls, traces, and intermediate files. Mark what
matters: unsupported claims, suspicious tool use, missing evidence, useful
examples, or follow-up items.

Return later and see what was already found.

```text
agent run → inspect → annotate → review later
```

**Note:** Because the CLI is scriptable, you can use a coding agent for bulk
annotation. For example: “Add a `needs_review` tag to every trajectory where the
final answer cites evidence that does not appear in the trace.”

SKIM stores annotations locally under `.skim/review.json`, so every surface reads
from the same source of truth.

## Demo

Annotate a review target from the CLI, then inspect it in the TUI or Web UI.

Demo GIF coming soon.

<!--
![SKIM demo](./docs/assets/skim-demo.gif)
-->

## Surfaces

SKIM is local-first and works across three surfaces:

- **CLI:** annotate files or structured review targets, discover valid targets,
  and support scriptable review workflows through `uv run skim ...` from the workspace root.
- **TUI:** browse folders, inspect files, explore JSON structures, and edit
  annotations from the terminal with `uv run skim <path>`.
- **Web UI:** review the same workspace in a localhost browser interface with
  `uv run skim-web <path>`.

All annotations stay inside the workspace. No server-side state, no external
database, no hidden project account.

## Example

Annotate a suspicious trajectory from the CLI:

```bash
uv run skim annotation examples/agent-run/trajectory.json \
  --label needs_review \
  --tag tool_mismatch \
  --note "The final answer mentions evidence that does not appear in the trace."
```

Open the same workspace in the TUI:

```bash
uv run skim examples/agent-run
```

Or inspect it in the Web UI:

```bash
uv run skim-web examples/agent-run
```

## What SKIM is for

SKIM is useful when reviewing local artifacts should leave a trail:

- reviewing traces and trajectories
- inspecting tool-call logs and model outputs
- annotating specific JSON nodes inside large structured files
- triaging generated files
- walking through JSON-heavy artifacts
- marking files or structured targets for follow-up
- keeping review notes close to the artifact being reviewed

SKIM starts smaller than a full agent evaluation platform. It focuses first on
structured inspection of messy local workspaces.

Over time, the same annotation layer can support export, filter/query workflows,
taxonomy-guided labels, MCP integration, automated review, and evaluation
tooling.

## Quickstart

Run SKIM from source:

```bash
git clone https://github.com/shizheng-rlfresh/skim.git
cd skim
uv sync
uv run skim .
```

Requires Python 3.12 or newer.

See [docs/usage.md](./docs/usage.md) for TUI, Web UI, and annotation CLI
commands.

## Documentation

- [Usage guide](./docs/usage.md)
- [Architecture](./docs/architecture.md)
- [Web UI design spec](./docs/skim-web-ui-spec.md)
- [Project overview](./docs/v1/overview.md)

## License

MIT
