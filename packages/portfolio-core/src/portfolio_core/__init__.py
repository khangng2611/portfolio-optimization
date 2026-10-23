"""Explicit-input deterministic numerical allocation."""

from .allocator import allocate
from .errors import CoreError
from .version import __version__

__all__ = ["allocate", "CoreError", "__version__"]
