"""C04 complete registration-path comparison with a NumPy transform challenger."""

import json
import statistics
import time
from unittest.mock import patch

import numpy as np
from aethron_edge.sensors.registration import Registration, RigCalibration, _point


def artifact():
    return RigCalibration(
        version=1,
        source_frame="radar",
        target_frame="optical",
        mount_id="fixture",
        evidence="synthetic",
        camera={"width": 640, "height": 480, "fx": 400.0, "fy": 400.0, "cx": 320.0, "cy": 240.0},
        rotation=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        translation_m=(0.5, 0.0, 0.0),
        translation_error_m=0.01,
        rotation_error_rad=0.001,
        reprojection_error_px=0.25,
    )


def numpy_transform(self, xyz_m):
    point = _point(xyz_m)
    result = np.asarray(self.rotation).reshape(3, 3) @ point + self.translation_m
    return tuple(_point(tuple(map(float, result))))


def main():
    calibration = artifact()
    scalar = RigCalibration.transform
    digest = RigCalibration.digest
    expected_digest = calibration.digest
    rotation = np.asarray(calibration.rotation).reshape(3, 3)
    translation = np.asarray(calibration.translation_m)

    def prepared_numpy(self, xyz_m):
        point = _point(xyz_m)
        return tuple(_point(tuple(map(float, rotation @ point + translation))))

    outputs = {}
    samples = {
        name: []
        for name in (
            "scalar",
            "numpy_transform",
            "prepared_numpy_transform",
            "cached_digest_prototype",
            "cached_numpy_prototype",
        )
    }

    def run():
        binding = Registration(
            calibration, now_ns=0, valid_for_ns=1_000_000_000, clock_id="fixture"
        )
        return [
            binding.project(
                (i / 200, 0.0, 5.0),
                measurement_error_m=0.02,
                source_frame="radar",
                mount_id="fixture",
                capture_ns=1_000_000,
                uncertainty_ns=0,
                clock_id="fixture",
                now_ns=2_000_000,
            )
            for i in range(64)
        ]

    for i in range(15):
        names = list(samples)
        for name in names[i % len(names) :] + names[: i % len(names)]:
            with (
                patch.object(
                    RigCalibration,
                    "transform",
                    prepared_numpy
                    if name.startswith("prepared")
                    else numpy_transform
                    if "numpy" in name
                    else scalar,
                ),
                patch.object(
                    RigCalibration,
                    "digest",
                    property(lambda self: expected_digest) if name.startswith("cached") else digest,
                ),
            ):
                start = time.process_time_ns()
                outputs[name] = run()
                samples[name].append((time.process_time_ns() - start) / 1e6)
    assert all(value == outputs["scalar"] for value in outputs.values())
    assert all(not o.live_evidence for o in outputs["scalar"])
    print(
        json.dumps(
            {
                "points": 64,
                "samples": 15,
                "includes_binding": True,
                "prepared_numpy_setup_excluded": True,
                "parity": True,
                "cpu_p50_ms": {name: statistics.median(values) for name, values in samples.items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
