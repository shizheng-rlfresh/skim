"""Web adapter package for skim."""

from .preview_serializer import serialize_preview
from .server import create_server, main, serve, static_dir

__all__ = ["create_server", "main", "serialize_preview", "serve", "static_dir"]
