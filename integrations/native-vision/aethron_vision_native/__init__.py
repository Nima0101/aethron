"""Output-admission contract v1. Requires caller-owned, unchanging input buffers."""

from ._bounds import validate_output

CONTRACT_VERSION = 1
__all__ = ["CONTRACT_VERSION", "validate_output"]
