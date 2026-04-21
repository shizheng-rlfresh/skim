# skim architecture

`skim` now uses one distributable Python package with explicit internal layers:

- `skim.core`: UI-neutral filesystem, preview, review, and normalization helpers.
- `skim.tui`: Textual shell, pane widgets, trajectory views, and TUI-only interactions.
- `skim.webui`: localhost server, preview serialization, and packaged browser assets.
- `skim.cli`: console entrypoint wiring for `skim`, `skim-dev`, and `skim-web`.

Compatibility surfaces remain in place:

- Top-level modules such as `skim.app`, `skim.preview`, `skim.review`, and `skim.server`
  alias the new adapter/core modules so existing imports and tests keep working.
- The browser shell is served from `skim.webui.static`, with `main.js` as the module
  entrypoint and responsibility-oriented module files alongside it.

Dependency direction:

- `skim.core` must not depend on Textual, the HTTP server, or browser code.
- `skim.tui` and `skim.webui` may depend on `skim.core`.
- `skim.cli` may depend on adapter packages.

This keeps behavior stable while making future CLI, agentic, and adapter-specific work
land in clearer ownership boundaries.
