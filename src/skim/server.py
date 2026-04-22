"""Compatibility exports for the localhost web server module."""

from .core.review import AnnotationStore
from .webui.server import SkimHandler, create_server, main, serve, static_dir

__all__ = ["AnnotationStore", "SkimHandler", "create_server", "main", "serve", "static_dir"]


if __name__ == "__main__":
    main()
