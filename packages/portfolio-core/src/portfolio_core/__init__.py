"""Explicit-input deterministic numerical allocation."""

from .allocator import allocate, validate_numerical_inputs
from .errors import CoreError
from .version import __version__

__all__ = ["allocate", "validate_numerical_inputs", "CoreError", "__version__"]
