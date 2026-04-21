"""Localhost web server for skim's Python-first browser UI.

The server is intentionally local-only. It serves static HTML/CSS/JS assets
from the installed package and exposes a small JSON API for browsing local
files, rendering typed preview payloads, and storing annotations under
``<browse-root>/.skim/review.json``.
"""

from __future__ import annotations

import json
import sys
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..core.filesystem import build_tree, resolve_browse_path
from ..core.review import AnnotationStore
from .preview_serializer import serialize_preview


class SkimHandler(SimpleHTTPRequestHandler):
    """Serve the bundled browser client and skim's local JSON API."""

    browse_root: Path
    store: AnnotationStore
    web_dir: Path

    def __init__(
        self,
        *args,
        browse_root: Path,
        store: AnnotationStore,
        web_dir: Path,
        **kwargs,
    ) -> None:
        """Initialize the request handler with one browse root and asset directory."""
        self.browse_root = browse_root.resolve()
        self.store = store
        self.web_dir = web_dir
        super().__init__(*args, directory=str(web_dir), **kwargs)

    def do_GET(self) -> None:
        """Route GET requests to the JSON API or bundled static assets."""
        parsed = urlparse(self.path)
        if parsed.path == "/api/tree":
            self._json_response(build_tree(self.browse_root))
            return
        if parsed.path == "/api/preview":
            self._serve_preview(parse_qs(parsed.query))
            return
        if parsed.path == "/api/annotations":
            self._json_response(self.store.payload)
            return
        if parsed.path == "/api/annotation-version":
            self._json_response({"annotation_version": self.store.annotation_version})
            return
        if parsed.path == "/api/triage":
            self._json_response(
                {
                    "annotation_version": self.store.annotation_version,
                    "items": [item.to_payload() for item in self.store.triage_items()],
                }
            )
            return
        super().do_GET()

    def do_POST(self) -> None:
        """Create or update one annotation entry."""
        if self.path != "/api/annotations":
            self._error(404, "Not found")
            return
        body = self._read_json_body()
        if body is None:
            return
        file_path = body.get("file")
        annotation_path = body.get("path")
        if not isinstance(file_path, str) or not isinstance(annotation_path, str):
            self._error(400, "Missing file/path fields")
            return
        tags = body.get("tags", [])
        if not isinstance(tags, list):
            self._error(400, "Tags must be a list")
            return
        note = body.get("note", "")
        if not isinstance(note, str):
            self._error(400, "Note must be a string")
            return
        annotation_id = body.get("annotation_id")
        if annotation_id is not None and not isinstance(annotation_id, str):
            self._error(400, "annotation_id must be a string")
            return

        source_path = self._resolve_browse_target(file_path)
        if source_path is None:
            self._error(403, "Forbidden")
            return
        if not source_path.is_file():
            self._error(404, "File not found")
            return

        if annotation_id:
            annotation = self.store.update_annotation(
                source_path,
                annotation_path,
                annotation_id,
                tags=tuple(str(tag) for tag in tags),
                note=note,
            )
            if annotation is None:
                self._error(404, "Annotation not found")
                return
        else:
            annotation = self.store.add_annotation(
                source_path,
                annotation_path,
                tags=tuple(str(tag) for tag in tags),
                note=note,
            )
        self._json_response(
            {
                "ok": True,
                "annotation": {
                    "id": annotation.id,
                    "created_at": annotation.created_at,
                    "updated_at": annotation.updated_at,
                    "tags": list(annotation.tags),
                    "note": annotation.note,
                },
            }
        )

    def do_DELETE(self) -> None:
        """Delete one annotation, if present."""
        if self.path != "/api/annotations":
            self._error(404, "Not found")
            return
        body = self._read_json_body()
        if body is None:
            return
        file_path = body.get("file")
        annotation_path = body.get("path")
        if not isinstance(file_path, str) or not isinstance(annotation_path, str):
            self._error(400, "Missing file/path fields")
            return

        source_path = self._resolve_browse_target(file_path)
        if source_path is None:
            self._error(403, "Forbidden")
            return
        if not source_path.is_file():
            self._error(404, "File not found")
            return

        annotation_id = body.get("annotation_id")
        if not isinstance(annotation_id, str):
            self._error(400, "Missing annotation_id field")
            return

        self.store.delete_annotation(source_path, annotation_path, annotation_id)
        self._json_response({"ok": True})

    def do_OPTIONS(self) -> None:
        """Return an empty same-origin-only preflight response."""
        self.send_response(204)
        self.end_headers()

    def _serve_preview(self, query_string: dict[str, list[str]]) -> None:
        """Serialize one local file into a browser preview payload."""
        relative_path = query_string.get("path", [""])[0]
        if not relative_path:
            self._error(400, "Missing path parameter")
            return

        target = self._resolve_browse_target(relative_path)
        if target is None:
            self._error(403, "Forbidden")
            return

        payload = serialize_preview(
            target,
            browse_root=self.browse_root,
            annotation_store=self.store,
        )
        status = 200
        if payload["kind"] == "error":
            status = 404 if "Not a file" in str(payload.get("message")) else 500
        self._json_response(payload, status=status)

    def _resolve_browse_target(self, relative_path: str) -> Path | None:
        """Return one browse-root-relative path or ``None`` when it escapes."""
        return resolve_browse_path(self.browse_root, relative_path)

    def _read_json_body(self) -> dict[str, object] | None:
        """Decode one JSON request body, responding with 400 on failure."""
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._error(400, "Invalid Content-Length")
            return None

        try:
            body = json.loads(self.rfile.read(content_length))
        except json.JSONDecodeError:
            self._error(400, "Invalid JSON body")
            return None
        if not isinstance(body, dict):
            self._error(400, "JSON body must be an object")
            return None
        return body

    def _json_response(self, data: object, *, status: int = 200) -> None:
        """Send one JSON response with the supplied status code."""
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status: int, message: str) -> None:
        """Send a structured JSON error response."""
        self._json_response({"error": message}, status=status)

    def log_message(self, format: str, *args) -> None:
        """Log only 4xx and 5xx responses to keep local runs readable."""
        status_code = str(args[0]) if args else ""
        if status_code.startswith("4") or status_code.startswith("5"):
            super().log_message(format, *args)


def create_server(path: str = ".", port: int = 8008) -> HTTPServer:
    """Return a configured localhost HTTP server for skim's browser UI."""
    browse_root = Path(path).expanduser().resolve()
    if not browse_root.is_dir():
        raise ValueError(f"{browse_root} is not a directory")

    handler = partial(
        SkimHandler,
        browse_root=browse_root,
        store=AnnotationStore(browse_root),
        web_dir=static_dir(),
    )
    return HTTPServer(("127.0.0.1", port), handler)


def static_dir() -> Path:
    """Return the packaged static web asset directory."""
    return Path(__file__).parent / "static"


def serve(path: str = ".", port: int = 8008) -> None:
    """Start the skim localhost web server."""
    try:
        server = create_server(path, port)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    browse_root = Path(path).expanduser().resolve()
    print(f"\n  skim web → http://localhost:{server.server_address[1]}")
    print(f"  browsing → {browse_root}")
    print("  scope    → localhost only\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        server.shutdown()


def main() -> None:
    """CLI entry point for ``skim-web``."""
    import argparse

    parser = argparse.ArgumentParser(description="skim web UI")
    parser.add_argument("path", nargs="?", default=".", help="Directory to browse")
    parser.add_argument("-p", "--port", type=int, default=8008, help="Port (default: 8008)")
    args = parser.parse_args()
    serve(args.path, args.port)


if __name__ == "__main__":
    main()
