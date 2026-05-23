# skim

SKIM is a lightweight file-system review and annotation tool for humans and AI
agents working over complex folders, codebases, datasets, and agent traces.

The core idea is simple: reading a file system should leave structured evidence
behind. Instead of inspecting files once and losing the context, SKIM lets users
annotate review targets from the CLI, TUI, or web UI, then revisit those
annotations as durable local review state.

Today, SKIM stores annotations in `<browse-root>/.skim/review.json`, supports
file-level annotations for non-JSON files, and supports UI-visible JSON targets
for structured artifacts such as agent trajectories. The first wedge is narrow
on purpose: make messy local file systems inspectable, reviewable, and
traceable without a database or external service.

## Why

Reviewing a local folder is often an ephemeral activity. A human opens files,
spots evidence, closes the tool, and the reasoning disappears. An agent later
reopens the same folder and has to guess from scratch.

SKIM aims to make that review memory explicit:

- mark files or JSON targets as important, suspicious, incomplete, useful, or
  needing review
- keep notes and tags next to the local artifact being reviewed
- let humans and agents share the same annotation source of truth
- turn file exploration into a repeatable, auditable workflow

SKIM is not trying to be a full agent evaluation platform at the beginning. Over
time, the same annotation layer can support agent handoff, taxonomy-guided
labels, MCP integration, query/export workflows, and evaluation tooling.

## Surfaces

- **TUI:** terminal-first folder browser with split panes, rich previews,
  structural JSON inspection, trajectory overlays, annotation editing, and
  workspace triage.
- **Web UI:** localhost browser UI backed by the same Python preview and
  annotation model.
- **CLI:** agent- and script-friendly `skim annotate ...` commands for
  discovering valid targets and mutating `.skim/review.json`.

All surfaces share local files as the source of truth. Review annotations remain
inside the browsed workspace under `.skim/review.json`.

## Demo

Demo GIF coming soon. The intended demo should show a local folder review flow:
opening a trajectory, inspecting evidence in the TUI or web UI, adding
annotations, and then listing those annotations from the CLI.

## Quickstart

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
