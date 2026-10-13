"""Output-admission contract v1. Requires caller-owned, unchanging input buffers."""

from ._bounds import pack_rgb, validate_output

CONTRACT_VERSION = 1
PACK_CONTRACT_VERSION = 1
__all__ = ["CONTRACT_VERSION", "PACK_CONTRACT_VERSION", "pack_rgb", "validate_output"]
