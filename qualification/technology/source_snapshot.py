"""Observe trusted checkout sources; this is not an execution attestation."""

import hashlib


def capture(root, names):
    """Hash a fixed caller-owned inventory before running synthetic controls."""
    try:
        return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}
    except OSError:
        raise RuntimeError("review_sources_unavailable") from None


def verify(root, snapshot):
    """Reject differing final observations without replacing the initial hashes."""
    if capture(root, snapshot) != snapshot:
        raise RuntimeError("review_sources_changed")
