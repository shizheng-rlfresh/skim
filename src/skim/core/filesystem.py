"""Filesystem helpers shared by skim adapters."""

from __future__ import annotations

from pathlib import Path

SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
}


def build_tree(root: Path, rel: Path | None = None) -> dict[str, object]:
    """Return a JSON-serializable directory tree rooted at ``root``."""
    if rel is None:
        rel = Path(".")

    abs_path = root / rel
    name = abs_path.name or str(root)
    if abs_path.is_file():
        return {
            "name": name,
            "type": "file",
            "ext": abs_path.suffix.lower(),
            "size": human_size(abs_path.stat().st_size),
            "path": str(rel),
        }

    children: list[dict[str, object]] = []
    try:
        entries = sorted(
            abs_path.iterdir(),
            key=lambda entry: (not entry.is_dir(), entry.name.lower()),
        )
    except PermissionError:
        entries = []

    for entry in entries:
        if entry.is_symlink():
            continue
        if entry.name in SKIP_DIRS:
            continue
        if entry.name.startswith(".") and entry.name != ".skim":
            continue
        children.append(build_tree(root, rel / entry.name))

    payload: dict[str, object] = {
        "name": name,
        "type": "dir",
        "path": str(rel),
        "children": children,
    }
    if rel == Path("."):
        payload["root_path"] = str(root)
    return payload


def resolve_browse_path(browse_root: Path, relative_path: str) -> Path | None:
    """Resolve one browse-root-relative path or return ``None`` when it escapes."""
    target = (browse_root.resolve() / relative_path).resolve()
    if not target.is_relative_to(browse_root.resolve()):
        return None
    return target


def human_size(size: int) -> str:
    """Return a short human-readable file size string."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"
