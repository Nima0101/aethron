"""Compare synthetic portable/native Cython wheels rebuilt from source archives."""

import argparse
import hashlib
import importlib.machinery
import io
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

SOURCE = b"def increment(value: int) -> int:\n    return value + 1\n"
common = """[build-system]
requires=[]
build-backend="BACKEND"
[project]
name="probe-native"
version="0.0.1"
requires-python=">=3.9"
license="GPL-3.0-only"
license-files=["LICENSE"]
"""
setup = """import os
from setuptools import setup, Extension
ext=[]
if os.environ.get("PROBE_NATIVE")=="1":
 from Cython.Build import cythonize
 ext=cythonize([Extension("probe_pkg.kernel",["probe_pkg/kernel.py"])],compiler_directives={"language_level":3,"annotation_typing":False},build_dir="build/cython")
setup(ext_modules=ext)
"""
meson = """project('probe-native', version: '0.0.1')
py = import('python').find_installation(pure: not get_option('native'))
py.install_sources('probe_pkg/__init__.py', 'probe_pkg/kernel.py', subdir: 'probe_pkg')
install_data('probe_pkg/schema.json', install_dir: py.get_install_dir() / 'probe_pkg')
if get_option('native')
 add_languages('c', native: false)
 c = custom_target('kernel-c', input: 'probe_pkg/kernel.py', output: 'kernel.c', command: [py, '-m', 'cython', '-3', '-X', 'annotation_typing=False', '@INPUT@', '-o', '@OUTPUT@'])
 py.extension_module('kernel', c, install: true, subdir: 'probe_pkg')
endif
"""
cmake = """cmake_minimum_required(VERSION 3.20)
project(probe_native LANGUAGES C)
option(PROBE_NATIVE "Compile synthetic kernel" OFF)
if(PROBE_NATIVE)
 find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
 add_custom_command(OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/kernel.c" COMMAND "${Python_EXECUTABLE}" -m cython -3 -X annotation_typing=False "${CMAKE_CURRENT_SOURCE_DIR}/probe_pkg/kernel.py" -o "${CMAKE_CURRENT_BINARY_DIR}/kernel.c" DEPENDS probe_pkg/kernel.py VERBATIM)
 Python_add_library(kernel MODULE "${CMAKE_CURRENT_BINARY_DIR}/kernel.c" WITH_SOABI)
 install(TARGETS kernel DESTINATION probe_pkg)
endif()
"""
candidates = {
    "setuptools": (
        "setuptools.build_meta",
        {"setup.py": setup},
        '[tool.setuptools.packages.find]\ninclude=["probe_pkg*"]\n[tool.setuptools.package-data]\nprobe_pkg=["*.json"]\n',
    ),
    "meson-python": (
        "mesonpy",
        {
            "meson.build": meson,
            "meson.options": "option('native', type: 'boolean', value: false)\n",
        },
        "",
    ),
    "scikit-build-core": (
        "scikit_build_core.build",
        {"CMakeLists.txt": cmake},
        '[tool.scikit-build]\nwheel.packages=["probe_pkg"]\nsdist.exclude=["unrelated-private-note.txt"]\n',
    ),
}


def extract_sdist(sdist, extracted):
    with tarfile.open(
        name=sdist if isinstance(sdist, (str, os.PathLike)) else None,
        fileobj=None if isinstance(sdist, (str, os.PathLike)) else sdist,
    ) as archive:
        members = archive.getmembers()
        assert len(members) <= 100
        assert not any(x.name.endswith("unrelated-private-note.txt") for x in members)
        for m in members:
            dest = extracted / m.name
            assert (
                dest.resolve().is_relative_to(extracted.resolve())
                and (m.isdir() or m.isfile())
                and m.size < 1024 * 1024
            )
            if m.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.extractfile(m).read())
    roots = list(extracted.iterdir())
    assert len(roots) == 1 and roots[0].is_dir()
    return roots[0]


def validate_wheel(whl, payload, native):
    with zipfile.ZipFile(whl) as z:
        names = z.namelist()
        for path, body in payload.items():
            assert z.read(path) == body
        extension = [
            n
            for n in names
            if n.startswith("probe_pkg/kernel.")
            and n.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES))
        ]
        assert len(extension) == int(native), (native, names)
        wheel = z.read(next(n for n in names if n.endswith(".dist-info/WHEEL"))).decode()
        assert ("Root-Is-Purelib: false" if native else "Root-Is-Purelib: true") in wheel
        tags = [line for line in wheel.splitlines() if line.startswith("Tag: ")]
        assert tags and all(line.endswith("-none-any") != native for line in tags)


def main():
    if sys.flags.optimize:
        raise SystemExit("probe_requires_assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backend", choices=["setuptools", "meson-python", "scikit-build-core"])
    options = parser.parse_args()
    ROOT = Path(__file__).resolve().parents[1]
    TOOLS = options.tools.resolve()
    OUT = options.out.resolve()
    OUT.mkdir(parents=True, exist_ok=False)
    ENV = dict(
        os.environ,
        PYTHONPATH=str(TOOLS),
        PATH=str(TOOLS / "bin") + os.pathsep + os.environ["PATH"],
        SOURCE_DATE_EPOCH="1767225600",
        CMAKE_BUILD_PARALLEL_LEVEL="1",
    )

    def run(args, cwd, log, env=ENV):
        p = subprocess.run(
            args, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=45
        )
        log.write_text(p.stdout + p.stderr)
        p.check_returncode()
        return p.stdout

    def hook(name, backend, project, method, out, native=False):
        out.mkdir()
        config = {}
        if name == "meson-python":
            config = {"setup-args": ["-Dnative=" + str(native).lower()], "compile-args": ["-j1"]}
        if name == "scikit-build-core":
            config = {
                "cmake.define.PROBE_NATIVE": "ON" if native else "OFF",
                "wheel.cmake": str(native).lower(),
            }
        env = dict(ENV, PROBE_NATIVE="1" if native else "0")
        if not native:
            env.update(CC="/nonexistent-probe-compiler", CXX="/nonexistent-probe-compiler")
        run(
            [
                sys.executable,
                "-c",
                "import sys,json,importlib;print(getattr(importlib.import_module(sys.argv[1]),sys.argv[2])(sys.argv[3],config_settings=json.loads(sys.argv[4])))",
                backend,
                method,
                str(out),
                json.dumps(config),
            ],
            project,
            out / "hook.log",
            env,
        )
        return next(out.glob("*.whl" if method == "build_wheel" else "*.tar.gz"))

    results = []
    for name, (backend, files, config) in candidates.items():
        if options.backend and name != options.backend:
            continue
        p = OUT / name
        p.mkdir()
        (p / "probe_pkg").mkdir()
        payload = {
            "probe_pkg/__init__.py": b"",
            "probe_pkg/kernel.py": SOURCE,
            "probe_pkg/schema.json": b'{"synthetic":true}\n',
        }
        for path, body in payload.items():
            (p / path).write_bytes(body)
        (p / "LICENSE").write_bytes((ROOT / "LICENSE").read_bytes())
        (p / "pyproject.toml").write_text(common.replace("BACKEND", backend) + config)
        for path, body in files.items():
            (p / path).write_text(body)
        # Source distributions use the committed synthetic fixture; no product tree or private file.
        for args in [
            ["init", "--quiet"],
            ["add", "probe_pkg", "LICENSE", "pyproject.toml", *files],
            [
                "-c",
                "user.name=Synthetic Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "--quiet",
                "-m",
                "synthetic fixture",
            ],
        ]:
            run(["git", *args], p, OUT / (name + "-git.log"))
        (p / "unrelated-private-note.txt").write_text("Must not enter wheel or sdist.\n")
        sdist = hook(name, backend, p, "build_sdist", OUT / (name + "-sdist"))
        extracted = OUT / (name + "-extracted")
        extracted.mkdir()
        sdist_bytes = sdist.read_bytes()
        sdist_sha256 = hashlib.sha256(sdist_bytes).hexdigest()
        src = extract_sdist(io.BytesIO(sdist_bytes), extracted)
        for path, body in payload.items():
            assert (src / path).read_bytes() == body
        for native in [False, True]:
            whl = hook(
                name,
                backend,
                src,
                "build_wheel",
                OUT / (name + ("-native" if native else "-pure")),
                native,
            )
            wheel_bytes = whl.read_bytes()
            wheel_sha256 = hashlib.sha256(wheel_bytes).hexdigest()
            validate_wheel(io.BytesIO(wheel_bytes), payload, native)
            target = OUT / (name + ("-native-install" if native else "-pure-install"))
            run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--no-deps",
                    "--force-reinstall",
                    "--require-hashes",
                    "--target",
                    str(target),
                    whl.as_uri() + "#sha256=" + wheel_sha256,
                ],
                OUT,
                OUT / (target.name + ".log"),
            )
            result = run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    'import sys,importlib.machinery;sys.path.insert(0,sys.argv[1]);from probe_pkg import kernel;assert kernel.increment(2**100)==2**100+1;assert kernel.increment(-2**100)==-2**100+1;native=kernel.__file__.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES));assert native==(sys.argv[2]=="1");print("synthetic-native-parity-ok")',
                    str(target),
                    "1" if native else "0",
                ],
                OUT,
                OUT / (target.name + "-run.log"),
            )
            results.append(
                {
                    "backend": name,
                    "native": native,
                    "wheel_sha256": wheel_sha256,
                    "sdist_sha256": sdist_sha256,
                    "result": result.strip(),
                }
            )
            (OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
            print(name, native, "PASS", flush=True)


if __name__ == "__main__":
    main()
