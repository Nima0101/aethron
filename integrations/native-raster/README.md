# Optional recorded Brown raster kernel

GPL-3.0-only C++20/CPython extension. Python remains the default/reference;
installing this package does not change any edge, ROS, live or model path.
It supports recorded LWIR/NIR mono8/mono16 Brown-Conrady remapping only.
Fisheye remains on the Python reference. No OEM SDK/device is accessed.

Build an ABI/platform-specific wheel with the installed C++20 compiler:

```sh
python -m pip wheel --no-deps --no-build-isolation -w build/native-wheels integrations/native-raster
```

Install that wheel into an environment containing `aethron-edge==0.1.0`.
The package has no native runtime dependency beyond the platform C++ runtime.
It requires CPython 3.11 or later; a wheel built on one OS/architecture/ABI is
not a portable appliance artifact. A source install requires a compiler.

```python
from aethron_raster_native import rectify_recorded

result = rectify_recorded(raw_raster, brown_lens_calibration)
# result.data: packed counts (mono16 little-endian), result.validity: 0/1 bytes
# result.sample(x, y): original unsigned count or None
assert result.live_evidence is False
```

The public Python binding runs the unchanged reference calibration/layout
validators. The internal C++ kernel separately validates numeric and memory
bounds; direct use of `_kernel` is not a calibration admission interface.
It holds the immutable input bytes while releasing the GIL, allocates only the
output data/mask at the binding, and allocates nothing within the pixel loop.
At 327680 output pixels these buffers occupy 655360+327680 bytes for mono16.
No map cache, persistent history, normalization or live authority is introduced.
Compiler fast-math and contraction are disabled to preserve rounding behavior.

Use the existing Python `rectify_mono8_recorded`/`rectify_mono16_recorded`
explicitly when the optional wheel is unavailable or for fisheye. Backend
selection is explicit; installation never silently switches a verified path.

```sh
python -I -m unittest discover -s integrations/native-raster/tests -v
python -I integrations/native-raster/tests/benchmark.py
# Optional, substantially slower allocation instrumentation:
python -I integrations/native-raster/tests/benchmark.py --memory
cmake -S integrations/native-raster -B build/native-checks -DAETHRON_SANITIZERS=ON
cmake --build build/native-checks
ctest --test-dir build/native-checks --output-on-failure
```

The workflow builds installed parity on Linux, macOS and Windows, and runs
Linux ASan/UBSan. Benchmarks compare five warm synthetic 640x512 calls using
wall/CPU time, with optional Python-traced allocations (not total RSS/native
heap). Test success is software evidence for the exact build only. ROS/OEM
integration, target-device latency/power, full release and physical
qualification remain pending.
