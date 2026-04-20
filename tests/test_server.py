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


def test_api_preview_uses_specialized_payload_for_wrapped_trajectory(tmp_path):
    """Wrapped local trajectories should use the typed trajectory preview payload."""
    test_file = tmp_path / "trajectory.json"
    test_file.write_text(json.dumps({"trajectory": sample_trajectory()}))

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
    assert tool_blocks[0]["annotation_path"] == "$.trajectory.steps[0].output[2]"
    assert tool_blocks[0]["input"]["annotation_path"] == "$.trajectory.steps[0].output[2]"
    assert tool_blocks[0]["output"]["annotation_path"] == "$.trajectory.steps[0].output[3]"


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
