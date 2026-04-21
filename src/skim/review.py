"""Compatibility alias for the shared review module."""

import sys

from .core import review as _review

sys.modules[__name__] = _review
