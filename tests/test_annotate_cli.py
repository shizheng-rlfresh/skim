"""CLI tests for agent-friendly annotation commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import sample_trajectory

from skim import cli
from skim.annotate_cli import main as annotate_main
from skim.review import FILE_ANNOTATION_KEY


def run_annotate(args: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    """Run the annotation CLI with JSON output and return its payload."""
    status = annotate_main([*args, "--json"])
    captured = capsys.readouterr()
    assert captured.err == ""
    assert status == 0
    return json.loads(captured.out)


def test_annotate_inspect_json_lists_annotatable_targets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Inspect should expose raw JSON and trajectory annotation paths for agents."""
    source = tmp_path / "output.json"
    source.write_text(
        json.dumps({"task": {"prompt": "Review this."}, "trajectory": sample_trajectory()})
    )

    payload = run_annotate(
        ["inspect", "--root", str(tmp_path), "--file", "output.json"],
        capsys,
    )

    targets = payload["targets"]
    paths = {target["path"] for target in targets}
    assert payload["file"] == "output.json"
    assert "$.task" in paths
    assert "$.trajectory.metadata" in paths
    assert "$.trajectory.steps[0].output[0]" in paths
    task_target = next(target for target in targets if target["path"] == "$.task")
    assert task_target["annotation_count"] == 0
    assert task_target["preview"]


def test_annotate_inspect_non_json_returns_file_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-JSON files should expose only the whole-file annotation target."""
    (tmp_path / "review.md").write_text("# Review\n\nNeeds a closer look.\n")

    payload = run_annotate(
        ["inspect", "--root", str(tmp_path), "--file", "review.md"],
        capsys,
    )

    assert payload["file"] == "review.md"
    assert payload["targets"] == [
        {
            "path": FILE_ANNOTATION_KEY,
            "label": "File",
            "kind": "file",
            "annotation_count": 0,
            "preview": "# Review",
        }
    ]


def test_annotate_add_list_update_and_delete_round_trip(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Annotation commands should mutate the existing review.json store."""
    (tmp_path / "output.json").write_text(json.dumps({"task": "Review this."}))

    created = run_annotate(
        [
            "add",
            "--root",
            str(tmp_path),
            "--file",
            "output.json",
            "--path",
            "$.task",
            "--tag",
            "issue",
            "--note",
            "Check the task prompt.",
        ],
        capsys,
    )
    annotation_id = created["annotation"]["id"]

    listed = run_annotate(["list", "--root", str(tmp_path), "--file", "output.json"], capsys)
    assert listed["items"][0]["id"] == annotation_id
    assert listed["items"][0]["tags"] == ["issue"]
    assert listed["items"][0]["note"] == "Check the task prompt."

    updated = run_annotate(
        [
            "update",
            "--root",
            str(tmp_path),
            "--file",
            "output.json",
            "--path",
            "$.task",
            "--id",
            annotation_id,
            "--note",
            "Updated task concern.",
        ],
        capsys,
    )
    assert updated["annotation"]["tags"] == ["issue"]
    assert updated["annotation"]["note"] == "Updated task concern."

    deleted = run_annotate(
        [
            "delete",
            "--root",
            str(tmp_path),
            "--file",
            "output.json",
            "--path",
            "$.task",
            "--id",
            annotation_id,
        ],
        capsys,
    )
    assert deleted["deleted"] == {
        "id": annotation_id,
        "file": "output.json",
        "path": "$.task",
    }
    assert run_annotate(["list", "--root", str(tmp_path)], capsys)["items"] == []


def test_annotate_update_rejects_noop(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Update should require at least one field to change."""
    (tmp_path / "output.json").write_text(json.dumps({"task": "Review this."}))
    created = run_annotate(
        [
            "add",
            "--root",
            str(tmp_path),
            "--file",
            "output.json",
            "--path",
            "$.task",
            "--note",
            "Check the task prompt.",
        ],
        capsys,
    )

    status = annotate_main(
        [
            "update",
            "--root",
            str(tmp_path),
            "--file",
            "output.json",
            "--path",
            "$.task",
            "--id",
            created["annotation"]["id"],
            "--json",
        ]
    )
    captured = capsys.readouterr()

    assert status == 2
    assert json.loads(captured.err) == {"error": "update requires --note or --tag"}


def test_annotate_rejects_files_outside_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI file paths should be constrained to the workspace root."""
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}")

    status = annotate_main(
        [
            "inspect",
            "--root",
            str(tmp_path),
            "--file",
            "../outside.json",
            "--json",
        ]
    )
    captured = capsys.readouterr()

    assert status == 2
    assert json.loads(captured.err) == {"error": "file is outside root"}


def test_skim_main_dispatches_annotate_without_launching_tui(monkeypatch) -> None:
    """The main skim command should route annotate subcommands before TUI parsing."""
    called: list[list[str]] = []

    monkeypatch.setattr(cli.annotate_cli, "main", lambda argv: called.append(list(argv)) or 0)

    assert cli.main(["annotate", "list", "--json"]) == 0
    assert called == [["list", "--json"]]
