"""Canonical permissions for staged core-wheel members."""

from pathlib import Path

from setuptools.command.bdist_wheel import bdist_wheel


class ReproducibleWheel(bdist_wheel):
    def write_wheelfile(self, wheelfile_base, **kwargs):
        super().write_wheelfile(wheelfile_base, **kwargs)
        # Match the edge builder: normalize after installation and metadata
        # creation, before ZIP serialization. Never chmod the source checkout.
        for path in Path(self.bdist_dir).rglob("*"):
            if path.is_file():
                path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
