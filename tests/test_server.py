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

from conftest import sample_trajectory

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
        item
        for step in payload["steps"]
        for item in step["items"]
        if item["kind"] == "tool"
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


def test_real_output_json_stays_in_json_inspector_and_keeps_trajectory_branch():
    """The repo's wrapped output artifact should keep the JSON-inspector tree shape."""
    repo_root = Path(__file__).resolve().parents[1]
    payload = serialize_preview(
        repo_root / "data" / "output.json",
        browse_root=repo_root,
    )

    assert payload["kind"] == "json_inspector"
    labels = [node["label"] for node in payload["tree"][:6]]
    assert labels[0] == "Taskid f0cb3b77-768f-4fa1-a856-38904b44bef3"
    assert labels[1].startswith("Task {")
    assert labels[2].startswith("Taskpath /app/tasks/f0cb3b77-768f-4fa1-a856-38904b44bef3")
    trajectory_node = next(node for node in payload["tree"] if node["path"] == "$.trajectory")
    assert [child["label"] for child in trajectory_node["children"][:3]] == [
        "Metadata",
        "Final Output",
        "Step 1",
    ]


def test_real_submission_json_serializes_structured_detail_blocks():
    """Human-facing JSON fields should serialize as structured detail, not one raw blob."""
    repo_root = Path(__file__).resolve().parents[1]
    payload = serialize_preview(
        repo_root / "data" / "Factors affecting WHPs - v2.json",
        browse_root=repo_root,
    )

    export_node = next(
        node for node in payload["tree"] if node["path"] == "$.export_task_data_json"
    )

    assert payload["kind"] == "json_inspector"
    assert export_node["detail"]["kind"] == "detail"
    section_titles = [
        block["title"]
        for block in export_node["detail"]["blocks"]
        if block["kind"] == "section"
    ]
    assert "Prompt" in section_titles
    assert "Task Solution" in section_titles
    assert "Grader Guidance" in section_titles


def test_real_hermes_json_keeps_transcript_labels_and_structured_summary():
    """Hermes transcript artifacts should keep summary labels and structured detail."""
    repo_root = Path(__file__).resolve().parents[1]
    payload = serialize_preview(
        repo_root / "data" / "hermes_trajectory.json",
        browse_root=repo_root,
    )

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
