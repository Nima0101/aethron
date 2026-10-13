# Optional native vision kernels

`aethron-vision-native` 0.2.0 implements output-admission contract 1. It validates
the pinned detector's native-endian float32 tensor `(1, 8400, 85)`. Geometry must
be finite; probability channels must be in `[0, 1]`. It returns a boolean for
tensor contents and raises fixed `ValueError("invalid_input")` for invalid buffer
metadata. The Python detector still admits the exact ndarray type, dtype and
shape before dispatch. No model parsing, inference, NMS or provider selection
runs in this module. Version 0.2.0 also exposes RGB packing contract 1, described below.

When installed, the detector uses the module for C-contiguous output. Other
layouts and installations without the optional package use the equivalent
NumPy checker. A broken installed module, incompatible contract, native error
or rejection fails closed; none triggers another checker. Installation therefore
opts into the native admission implementation, never another inference provider.

The validation C loop uses the CPython buffer API with an explicit contiguous request and
checks dimensionality, byte length, item size and native float format before
reading. It keeps the GIL and buffer export, uses `memcpy` for unaligned values,
releases the export on every exit, and retains no input pointer. Caller-owned
buffers must not change during validation or subsequent postprocessing. This is
not a defense against an in-process malicious native buffer exporter.

The wheel targets CPython's 3.11 stable ABI. Linux x86-64 / CPython 3.13 was
locally built and tested; other systems and hosted sanitizer execution remain
unqualified. No NumPy C ABI, JIT, GPU, new thread pool or fast-math build is used.

Build with the pinned tools and installed vision dependencies:

```sh
python -m pip install setuptools==84.0.0 wheel==0.48.0
python -m pip wheel --no-deps --no-build-isolation integrations/native-vision --wheel-dir build/native-vision
python -m pip install --no-deps --no-index build/native-vision/*.whl
python -m unittest discover -s integrations/native-vision/tests -p test_bounds.py -v
python -m scripts.vision_admission_audit
```

The bounded profile reports all five wall/CPU timing samples per implementation
and layout, plus separately traced scratch allocation. Native heap accounting,
process RSS, inference latency and hardware qualification are outside its scope.
The provider workflow tests portable and installed-native paths and preserves
the wheel, profile and fault logs; a separate hosted job runs UBSan/bounds checks.

## RGB packing contract 1

`pack_rgb(source, output)` accepts a contiguous uint8 `(640,640,3)` RGB canvas
and a writable native float32 `(1,3,640,640)` output. It checks both buffer
descriptions and rejects overlapping address ranges before writing. It converts
each channel without scaling, color swaps or interpolation. Buffer exports and
the GIL remain held through the bounded loop; no pointer is retained. Unaligned
output is handled with `memcpy`. Invalid metadata raises the fixed invalid-input
error without changing the output. Success returns `True`.

The detector allocates its own canvas and output. OpenCV still performs the same
linear resize, with the same integer rounding and 114 top-left padding. A
one-pixel dimension that rounds to zero now fails with `invalid_input` before
OpenCV is called; it is not clamped. Package 0.1.x has no packing contract and
continues using NumPy packing. An absent package does likewise. A declared but
incompatible packing contract, rejection or exception fails closed before inference.

Preprocessing comparisons retain mixed timings, including a largest-input CPU
regression in one shared-host sample set. Native packing is not a universal
speedup or inference-latency claim. Build the tiny comparison probe and run:

```sh
cc -std=c11 -O3 -fno-fast-math -shared -fPIC tests/probes/vision_pack.c -o build/native-vision/pack.so
python -m scripts.vision_preprocess_audit --probe build/native-vision/pack.so
```
