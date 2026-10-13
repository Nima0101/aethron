"""Small optional CPU validator; finite checks require strict floating-point semantics."""

import sys

from setuptools import Extension, setup

setup(
    ext_modules=[
        Extension(
            "aethron_vision_native._bounds",
            ["aethron_vision_native/bounds.c"],
            define_macros=[("Py_LIMITED_API", "0x030b0000")],
            py_limited_api=True,
            extra_compile_args=["/std:c11", "/O2", "/fp:strict"]
            if sys.platform == "win32"
            else [
                "-std=c11",
                "-O3",
                "-fno-fast-math",
                "-ffp-contract=off",
                "-Wall",
                "-Wextra",
                "-Werror",
            ],
        )
    ],
    options={"bdist_wheel": {"py_limited_api": "cp311"}},
)
