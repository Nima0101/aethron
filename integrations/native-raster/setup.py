"""No fast-math/FMA contraction: reference rounding is part of pixel selection."""

import sys

from setuptools import Extension, setup

setup(
    ext_modules=[
        Extension(
            "aethron_raster_native._kernel",
            ["aethron_raster_native/binding.cpp"],
            language="c++",
            extra_compile_args=["/std:c++20", "/O2", "/fp:strict"]
            if sys.platform == "win32"
            else ["-std=c++20", "-O3", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror"],
        )
    ]
)
