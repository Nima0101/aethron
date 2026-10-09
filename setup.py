"""Explicit optional native wheel; default builds keep the portable Python runtime."""

import os

from setuptools import Extension, setup

native = os.environ.get("AETHRON_BUILD_NATIVE_BOUNDS", "0")
if native not in ("0", "1"):
    raise RuntimeError("invalid_native_bounds_build_selection")
extensions = []
if native == "1":
    import Cython
    from Cython.Build import cythonize

    if Cython.__version__ != "3.3.0":
        raise RuntimeError("install_pinned_native_build_requirements")
    extensions = cythonize(
        [
            Extension(
                "aethron._json_bounds",
                ["aethron/_json_bounds.py"],
                depends=["aethron/_json_bounds.pxd"],
            )
        ],
        compiler_directives={"language_level": 3},
        build_dir="build/native-bounds-c",
    )
setup(ext_modules=extensions)
