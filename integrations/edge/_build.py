"""Canonical permissions for staged edge-wheel members."""

from pathlib import Path

from setuptools.command.bdist_wheel import bdist_wheel


class ReproducibleWheel(bdist_wheel):
    def write_wheelfile(self, wheelfile_base, **kwargs):
        super().write_wheelfile(wheelfile_base, **kwargs)
        # This hook runs after installation and metadata creation, before ZIP
        # serialization. Normalize only the staging tree, never source files.
        for path in Path(self.bdist_dir).rglob("*"):
            if path.is_file():
                path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
