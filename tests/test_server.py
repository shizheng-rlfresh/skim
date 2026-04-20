"""HTTP API tests for the skim localhost web server."""

from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
from contextlib import contextmanager
from functools import partial
from http.server import HTTPServer
from pathlib import Path

from conftest import sample_hermes_transcript, sample_submission, sample_trajectory

from skim.server import AnnotationStore, SkimHandler
from skim.web_preview import serialize_preview


@contextmanager
def running_server(root: Path):
    """Yield a running local skim HTTP server bound to an ephemeral port."""
    web_dir = Path(__file__).resolve().parents[1] / "src" / "skim" / "web"
    server = HTTPServer(
        ("127.0.0.1", 0),
        partial(
            SkimHandler,
            browse_root=root,
            store=AnnotationStore(root),
            web_dir=web_dir,
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
) -> tuple[int, dict]:
    """Return the JSON response body for one request."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        base_url + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            status = response.status
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        status = error.code
        payload = json.loads(error.read().decode())
    return status, payload


def test_api_preview_returns_text_payload_for_plain_file(tmp_path):
    """The preview API should classify plain source files as text payloads."""
    test_file = tmp_path / "example.py"
    test_file.write_text("print('hello')\n")

    with running_server(tmp_path) as base_url:
        status, payload = request_json(
            base_url,
            "/api/preview?path=" + urllib.parse.quote("example.py"),
        )

    assert status == 200
    assert payload["kind"] == "text"
    assert payload["path"] == "example.py"
    assert payload["language"] == "python"
    assert "print('hello')" in payload["content"]
    assert payload["render"]["kind"] == "syntax"
    assert payload["render"]["language"] == "python"
    assert payload["render"]["line_numbers"] is True
    assert "tok-nb" in payload["render"]["html"] or "tok-n" in payload["render"]["html"]


def test_api_preview_falls_back_to_text_for_invalid_json(tmp_path):
    """Malformed JSON should degrade to a text preview instead of crashing."""
    test_file = tmp_path / "broken.json"
    test_file.write_text("{not json")

    with running_server(tmp_path) as base_url:
        status, payload = request_json(
            base_url,
            "/api/preview?path=" + urllib.parse.quote("broken.json"),
        )

    assert status == 200
    assert payload["kind"] == "text"
    assert payload["language"] == "json"
    assert payload["content"] == "{not json"


def test_api_preview_uses_explicit_notebook_payload(tmp_path):
    """Notebook files should get a dedicated preview kind with flattened cells."""
    test_file = tmp_path / "notebook.ipynb"
    test_file.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": ["# Title\n", "\n", "Notebook body\n"],
                    },
                    {
                        "cell_type": "code",
                        "metadata": {},
                        "source": ["print('hi')\n"],
                        "outputs": [
                            {"output_type": "stream", "name": "stdout", "text": ["hi\n"]},
                        ],
                    },
                ],
                "metadata": {"language_info": {"name": "python"}},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        )
    )

    with running_server(tmp_path) as base_url:
        status, payload = request_json(
            base_url,
            "/api/preview?path=" + urllib.parse.quote("notebook.ipynb"),
        )

    assert status == 200
    assert payload["kind"] == "notebook"
    assert payload["language"] == "python"
    assert payload["summary"]["cell_count"] == 2
    assert payload["cells"][0]["kind"] == "markdown"
    assert payload["cells"][1]["kind"] == "code"
    assert payload["cells"][1]["render"]["kind"] == "syntax"
    assert payload["cells"][1]["outputs"][0]["render"]["kind"] == "text"


def test_api_preview_invalid_notebook_falls_back_to_text(tmp_path):
    """Broken notebook JSON should still degrade to a syntax-highlighted text preview."""
    test_file = tmp_path / "broken.ipynb"
    test_file.write_text("{not json")

    with running_server(tmp_path) as base_url:
        status, payload = request_json(
            base_url,
            "/api/preview?path=" + urllib.parse.quote("broken.ipynb"),
        )

    assert status == 200
    assert payload["kind"] == "text"
    assert payload["language"] == "json"
    assert payload["render"]["kind"] == "syntax"


def test_api_preview_keeps_wrapped_trajectory_in_json_inspector(tmp_path):
    """Wrapped local trajectories should stay in the unified JSON inspector."""
    test_file = tmp_path / "trajectory.json"
    test_file.write_text(json.dumps({"trajectory": sample_trajectory()}))

    with running_server(tmp_path) as base_url:
        status, payload = request_json(
            base_url,
            "/api/preview?path=" + urllib.parse.quote("trajectory.json"),
        )

    assert status == 200
    assert payload["kind"] == "json_inspector"
    labels = [node["label"] for node in payload["tree"][:4]]
    assert labels == ["Metadata", "Final Output", "Step 1", "Trajectory {4}"]
    trajectory_node = next(node for node in payload["tree"] if node["path"] == "$.trajectory")
    child_labels = [child["label"] for child in trajectory_node["children"][:3]]
    assert child_labels == ["Metadata", "Final Output", "Step 1"]


def test_json_inspector_nodes_include_display_metadata_for_raw_values(tmp_path):
    """JSON tree nodes should expose structured display metadata for the browser tree."""
    test_file = tmp_path / "plain.json"
    test_file.write_text(
        json.dumps(
            {
                "name": "skim",
                "count": 3,
                "ok": True,
                "missing": None,
                "items": [1, 2],
            }
        )
    )

    payload = serialize_preview(test_file, browse_root=tmp_path)
    name_node = next(node for node in payload["tree"] if node["path"] == "$.name")
    count_node = next(node for node in payload["tree"] if node["path"] == "$.count")
    ok_node = next(node for node in payload["tree"] if node["path"] == "$.ok")
    missing_node = next(node for node in payload["tree"] if node["path"] == "$.missing")
    items_node = next(node for node in payload["tree"] if node["path"] == "$.items")

    assert payload["kind"] == "json_inspector"
    assert name_node["display_key"] == "name"
    assert name_node["display_value"] == '"skim"'
    assert name_node["value_type"] == "string"
    assert name_node["node_class"] == "string"
    assert name_node["synthetic"] is False
    assert count_node["display_value"] == "3"
    assert count_node["value_type"] == "number"
    assert ok_node["display_value"] == "true"
    assert ok_node["value_type"] == "boolean"
    assert missing_node["display_value"] == "null"
    assert missing_node["value_type"] == "null"
    assert items_node["display_value"] == "[2]"
    assert items_node["value_type"] == "array"


def test_json_inspector_nodes_include_overlay_display_metadata(tmp_path):
    """Synthetic overlay nodes should expose explicit node classes for icon rendering."""
    test_file = tmp_path / "trajectory.json"
    test_file.write_text(json.dumps({"trajectory": sample_trajectory()}))

    payload = serialize_preview(test_file, browse_root=tmp_path)
    metadata_node = next(node for node in payload["tree"] if node["label"] == "Metadata")
    step_node = next(node for node in payload["tree"] if node["label"] == "Step 1")

    assert metadata_node["synthetic"] is True
    assert metadata_node["node_class"] == "trajectory_metadata"
    assert metadata_node["display_key"] == "Metadata"
    assert step_node["synthetic"] is True
    assert step_node["node_class"] == "trajectory_step"
    assert step_node["display_key"] == "Step 1"


def test_api_preview_uses_specialized_payload_for_bare_trajectory(tmp_path):
    """Bare trajectory files should still use the dedicated trajectory preview."""
    test_file = tmp_path / "trajectory.json"
    test_file.write_text(json.dumps(sample_trajectory()))

    with running_server(tmp_path) as base_url:
        status, payload = request_json(
            base_url,
            "/api/preview?path=" + urllib.parse.quote("trajectory.json"),
        )

    assert status == 200
    assert payload["kind"] == "trajectory"
    assert payload["steps"]
    tool_blocks = [
        item for step in payload["steps"] for item in step["items"] if item["kind"] == "tool"
    ]
    assert tool_blocks
    assert tool_blocks[0]["annotation_path"] == "$.steps[0].output[2]"
    assert tool_blocks[0]["input"]["annotation_path"] == "$.steps[0].output[2]"
    assert tool_blocks[0]["output"]["annotation_path"] == "$.steps[0].output[3]"


def test_api_preview_rejects_paths_outside_browse_root(tmp_path):
    """The preview endpoint should reject traversal outside the browse root."""
    outside_file = tmp_path.parent / "outside.txt"
    outside_file.write_text("secret\n")

    with running_server(tmp_path) as base_url:
        status, payload = request_json(
            base_url,
            "/api/preview?path=" + urllib.parse.quote("../outside.txt"),
        )

    assert status == 403
    assert payload == {"error": "Forbidden"}


def test_api_annotations_round_trip_to_review_json(tmp_path):
    """Saving and deleting annotations should preserve skim's review.json contract."""
    test_file = tmp_path / "plain.json"
    test_file.write_text(json.dumps({"hello": "world"}))

    with running_server(tmp_path) as base_url:
        save_status, save_payload = request_json(
            base_url,
            "/api/annotations",
            method="POST",
            body={
                "file": "plain.json",
                "path": "$.hello",
                "tags": ["important"],
                "note": "keep this",
            },
        )
        _, preview = request_json(
            base_url,
            "/api/preview?path=" + urllib.parse.quote("plain.json"),
        )
        get_status, stored = request_json(base_url, "/api/annotations")
        delete_status, delete_payload = request_json(
            base_url,
            "/api/annotations",
            method="DELETE",
            body={"file": "plain.json", "path": "$.hello"},
        )
        _, after_delete = request_json(base_url, "/api/annotations")

    assert save_status == 200
    assert save_payload == {"ok": True}
    assert get_status == 200
    assert stored["files"]["plain.json"]["annotations"]["$.hello"] == {
        "tags": ["important"],
        "note": "keep this",
    }
    hello_node = next(node for node in preview["tree"] if node["path"] == "$.hello")
    assert hello_node["annotation"] == {"tags": ["important"], "note": "keep this"}
    assert delete_status == 200
    assert delete_payload == {"ok": True}
    assert after_delete["files"]["plain.json"]["annotations"] == {}


def test_root_serves_local_static_shell_without_cdn_dependencies(tmp_path):
    """The browser shell should be bundled local assets, not CDN React scripts."""
    with running_server(tmp_path) as base_url:
        request = urllib.request.Request(base_url + "/")
        with urllib.request.urlopen(request) as response:
            html = response.read().decode()

    assert "app.js" in html
    assert "styles.css" in html
    assert "unpkg.com" not in html
    assert "text/babel" not in html


def test_stylesheet_includes_syntax_theme_classes(tmp_path):
    """The checked-in stylesheet should include token classes for syntax HTML."""
    with running_server(tmp_path) as base_url:
        request = urllib.request.Request(base_url + "/styles.css")
        with urllib.request.urlopen(request) as response:
            css = response.read().decode()

    assert ".syntax-block" in css
    assert ".tok-k" in css


def test_stylesheet_bundles_font_face_and_light_theme_tokens(tmp_path):
    """The bundled stylesheet should ship local fonts and both shell themes."""
    with running_server(tmp_path) as base_url:
        request = urllib.request.Request(base_url + "/styles.css")
        with urllib.request.urlopen(request) as response:
            css = response.read().decode()

    assert "@font-face" in css
    assert "JetBrains Mono" in css
    assert ':root[data-theme="light"]' in css
    assert "--syn-keyword" in css


def test_stylesheet_locks_preview_panes_to_the_viewport(tmp_path):
    """The web shell should keep panes height-constrained and scrolling internally."""
    with running_server(tmp_path) as base_url:
        request = urllib.request.Request(base_url + "/styles.css")
        with urllib.request.urlopen(request) as response:
            css = response.read().decode()

    assert ".app-shell" in css
    assert "height: 100vh;" in css
    assert ".workspace" in css
    assert "overflow: hidden;" in css
    assert ".preview-work" in css
    assert ".pane-grid" in css
    assert "grid-auto-rows: minmax(0, 1fr);" in css


def test_stylesheet_increases_preview_readability_defaults(tmp_path):
    """Preview content should use larger default type and more relaxed line spacing."""
    with running_server(tmp_path) as base_url:
        request = urllib.request.Request(base_url + "/styles.css")
        with urllib.request.urlopen(request) as response:
            css = response.read().decode()

    assert ".pane-content" in css
    assert "font-size: 15px;" in css
    assert "line-height: 1.6;" in css
    assert ".text-block" in css
    assert ".detail-panel,\n.step-detail" in css or ".detail-panel,\r\n.step-detail" in css
    assert ".tree-row" in css
    assert "padding: 9px 12px;" in css


def test_stylesheet_defines_file_and_json_color_tokens(tmp_path):
    """The stylesheet should include tree/icon color tokens for files and JSON nodes."""
    with running_server(tmp_path) as base_url:
        request = urllib.request.Request(base_url + "/styles.css")
        with urllib.request.urlopen(request) as response:
            css = response.read().decode()

    assert "--file-kind-python" in css
    assert "--file-kind-directory" in css
    assert "--file-kind-archive" in css
    assert "--json-type-string" in css
    assert "--json-type-boolean" in css
    assert ".file-icon" in css
    assert ".json-node-icon" in css


def test_stylesheet_defines_annotation_and_sidebar_resize_states(tmp_path):
    """The stylesheet should include stronger annotation states and resize-handle rules."""
    with running_server(tmp_path) as base_url:
        request = urllib.request.Request(base_url + "/styles.css")
        with urllib.request.urlopen(request) as response:
            css = response.read().decode()

    assert ".annotate-button" in css
    assert ".annotate-button-pending" in css
    assert ".annotate-button-active" in css
    assert ".json-tree-row-annotated" in css
    assert ".annotation-glyph" in css
    assert ".sidebar-resizer" in css
    assert ".app-shell.sidebar-resizing" in css
    assert ".json-fallback-key" in css


def test_stylesheet_defines_palette_and_split_resize_states(tmp_path):
    """The stylesheet should include palette contrast hooks and shared split resizers."""
    with running_server(tmp_path) as base_url:
        request = urllib.request.Request(base_url + "/styles.css")
        with urllib.request.urlopen(request) as response:
            css = response.read().decode()

    assert ".palette-name" in css
    assert ".palette-path" in css
    assert ".split-resizer" in css
    assert ".pane-row" in css
    assert ".pane-row-resizer" in css
    assert ".pane-grid.layout-grid" in css


def test_status_bar_copy_and_typography_match_current_behavior(tmp_path):
    """The shell should only advertise working hints and use larger footer text."""
    with running_server(tmp_path) as base_url:
        with urllib.request.urlopen(base_url + "/") as response:
            html = response.read().decode()
        with urllib.request.urlopen(base_url + "/styles.css") as response:
            css = response.read().decode()

    assert "Esc close" not in html
    assert "⌘B sidebar" in html
    assert "⌘K search" in html
    assert ".status-bar" in css
    assert "font-size: 13px;" in css


def test_wrapped_output_json_stays_in_json_inspector_and_keeps_trajectory_branch(tmp_path):
    """Wrapped output artifacts should keep raw keys plus trajectory overlay children."""
    test_file = tmp_path / "output.json"
    test_file.write_text(
        json.dumps(
            {
                "task_id": "task-123",
                "task": {"prompt": "Compare spray diary information."},
                "task_path": "/app/tasks/task-123",
                "trajectory": sample_trajectory(),
            }
        )
    )

    payload = serialize_preview(test_file, browse_root=tmp_path)

    assert payload["kind"] == "json_inspector"
    labels = [node["label"] for node in payload["tree"][:4]]
    assert labels[0] == "Task Id task-123"
    assert labels[1].startswith("Task {")
    assert labels[2] == "Task Path /app/tasks/task-123"
    assert labels[3].startswith("Trajectory {")
    trajectory_node = next(node for node in payload["tree"] if node["path"] == "$.trajectory")
    assert [child["label"] for child in trajectory_node["children"][:3]] == [
        "Metadata",
        "Final Output",
        "Step 1",
    ]


def test_submission_json_serializes_structured_detail_blocks(tmp_path):
    """Human-facing JSON fields should serialize as structured detail, not one raw blob."""
    submission = sample_submission()
    submission["export_task_data_json"] = {
        "prompt": "Compare spray diary information.",
        "task_solution": "Chlorpyrifos appears slower to decay than expected.",
        "agentic_grader_guidance": "Identify Chlorpyrifos.",
        "review": {"summary": "Looks good."},
    }
    test_file = tmp_path / "submission.json"
    test_file.write_text(json.dumps(submission))

    payload = serialize_preview(
        test_file,
        browse_root=tmp_path,
    )

    export_node = next(
        node for node in payload["tree"] if node["path"] == "$.export_task_data_json"
    )

    assert payload["kind"] == "json_inspector"
    assert export_node["detail"]["kind"] == "detail"
    fields_block = next(
        block for block in export_node["detail"]["blocks"] if block["kind"] == "fields"
    )
    field_labels = [field["label"] for field in fields_block["fields"]]
    assert "Prompt" in field_labels
    assert "Task Solution" in field_labels
    assert "Grader Guidance" in field_labels


def test_json_detail_blocks_include_syntax_html_for_raw_objects(tmp_path):
    """Raw JSON detail blocks should include highlighted HTML for structured values."""
    test_file = tmp_path / "plain.json"
    test_file.write_text(json.dumps({"plan": {"step": 1, "done": False}}))

    payload = serialize_preview(test_file, browse_root=tmp_path)
    plan_node = next(node for node in payload["tree"] if node["path"] == "$.plan")

    assert payload["kind"] == "json_inspector"
    assert plan_node["detail"]["kind"] == "detail"
    syntax_block = plan_node["detail"]["blocks"][0]
    assert syntax_block["kind"] == "syntax"
    assert syntax_block["language"] == "json"
    assert syntax_block["line_numbers"] is False
    assert "tok-nt" in syntax_block["html"] or "tok-n" in syntax_block["html"]


def test_hermes_json_keeps_transcript_labels_and_structured_summary(tmp_path):
    """Hermes transcript artifacts should keep summary labels and structured detail."""
    test_file = tmp_path / "hermes_trajectory.json"
    test_file.write_text(json.dumps(sample_hermes_transcript()))

    payload = serialize_preview(test_file, browse_root=tmp_path)

    summary_node = payload["tree"][0]
    conversations_node = next(
        node for node in payload["tree"] if node["label"].startswith("Conversations ")
    )

    assert payload["kind"] == "json_inspector"
    assert summary_node["label"] == "Transcript Summary"
    assert summary_node["detail"]["kind"] == "detail"
    fields_block = next(
        block for block in summary_node["detail"]["blocks"] if block["kind"] == "fields"
    )
    field_labels = [field["label"] for field in fields_block["fields"]]
    assert "model" in field_labels
    assert "timestamp" in field_labels
    assert "conversations" in field_labels
    assert conversations_node["children"][0]["label"].startswith("[0] System")
