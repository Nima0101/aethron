> Historical v0.1 evidence/procedure. See the [current v3 record](releasing-v3.md).

# Release engineering
A clean committed source revision is the release input. Run every S, D and V2 gate, then `python3 scripts/reproduce.py`. It clones without local hardlinks, executes the README quickstart, validates an external zipapp library consumer and compares two independent artifact builds byte-for-byte. `python3 scripts/release.py` creates deterministic source/zipapp artifacts, source hashes, CycloneDX SBOM and local provenance. Python itself is supplied by the consumer and is not embedded.

Optional conventional wheel: install pinned build tools, then `SOURCE_DATE_EPOCH=1767225600 python -m build --no-isolation`. Verify installation in an isolated environment outside the repository. Do not publish to a registry merely because packaging works.

Publication is blocked until all mandatory software, darkness, v2 and presentation checks pass, including the remaining real-browser visualization check. Public push has not occurred. After publication, run actual CI/CodeQL and anonymous clone verification before a release tag. Candidate-artifact workflow can create hosted attestations, but has not run. Only tag source that matches those checks; download assets and verify SHA-256/attestation before a release-readiness claim. H02/H03 remain required for physical production support regardless of reference-software release status.

The runtime/zipapp works on Python 3.9+; the pinned setuptools/build toolchain requires Python 3.10+ and was exercised on Python 3.13.15. `python scripts/package_check.py` performs two deterministic wheel builds and a fresh isolated installation; run it with the development environment's interpreter. This does not broaden platform or live-hardware support claims.
