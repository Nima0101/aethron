"""Explicit native clock wheel; portable builds retain the same Python source."""

import os

from setuptools import Extension, setup

native = os.environ.get("AETHRON_BUILD_NATIVE_CLOCK", "0")
if native not in ("0", "1"):
    raise RuntimeError("invalid_native_clock_build_selection")
extensions = []
if native == "1":
    import Cython
    from Cython.Build import cythonize

    if Cython.__version__ != "3.3.0":
        raise RuntimeError("install_pinned_native_build_requirements")
    extensions = cythonize(
        [Extension("aethron_edge.timebase", ["aethron_edge/timebase.py"])],
        # Clock integers are arbitrary-precision; annotations must not narrow them.
        compiler_directives={"language_level": 3, "annotation_typing": False},
        build_dir="build/native-clock-c",
    )
setup(ext_modules=extensions)
