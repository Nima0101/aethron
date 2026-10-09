# Optional native JSON resource guard

A native AETHRON wheel compiles the bounded JSON byte scan with Cython 3.3.0.
The same `_json_bounds.py` implements the portable fallback; an augmenting `.pxd`
adds C types without a runtime compiler dependency. Both paths enforce exact bytes,
65536 bytes and depth eight before JSON allocation. Duplicate keys, UTF-8, numeric
values, schema validation and fixed errors retain their existing decoder path.
The guard does not validate JSON syntax on its own.

Build with the project's pinned setuptools/wheel versions and the hash-locked
build-only compiler:

Use setuptools 82.0.1 on Python 3.9 and setuptools 84.0.0 on Python 3.10+;
wheel 0.48.0 supports both. These choices are also encoded in `pyproject.toml`.

```sh
python -m pip install --no-deps --require-hashes -r requirements-native.lock
AETHRON_BUILD_NATIVE_BOUNDS=1 python -m pip wheel --no-deps --no-build-isolation -w build/native-wheels .
```

On PowerShell, set `$env:AETHRON_BUILD_NATIVE_BOUNDS = '1'` before the wheel command.
Unset the variable for ordinary portable wheels. The native wheel is specific to
its Python ABI, OS and architecture. Install the selected wheel offline with
`pip install --no-index --no-deps /path/to/wheel.whl`; deployment and signed appliance
manifests must bind that exact artifact. Merely installing a compiler does not
change an existing runtime. Do not mix wheel variants in one deployment wheelhouse.

With the native wheel installed, run outside checkout imports:

```sh
AETHRON_EXPECT_NATIVE_BOUNDS=1 python -I -m unittest discover -s tests -p test_json_bounds.py -v
python -I scripts/json_bounds_compare.py --require-native
```

The comparison includes a Python loop, compiled-regex token iteration and the
installed guard on ordinary frames, maximum padding, dense brackets and escaped
strings, plus full parsing and 24-frame replay. Timing and Python-traced allocation
are diagnostic; neither is a worst-case latency, RSS or field qualification claim.
CI exercises installed core/parity on three OSes and two Python versions, with a
separate Linux ASan/UBSan job. Leak detection is disabled only for the unsanitized
host interpreter; address/undefined-behavior errors remain fatal.

Technology decision: compile the measured byte-loop bottleneck using
[Cython augmenting declarations](https://cython.readthedocs.io/en/latest/src/tutorial/pure.html#magic-attributes-within-the-pxd),
which preserves one algorithm source; the regex candidate degrades on dense input,
and a full native JSON replacement needs explicit
[duplicate-key handling](https://serde.rs/deserialize-map.html) and broader parity.
The build compiler is Apache-2.0; AETHRON code remains GPL-3.0-only. Native wheels
remain candidates until their applicable packaging, security and release gates pass.
