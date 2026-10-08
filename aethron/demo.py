"""Original synthetic scenarios. No live feed or real detection accuracy claim."""

import json

from .adapters import coarse_cue, depth_patch, envelope, person_cue, thermal_patch
from .core import evaluate


def scenarios():
    args = {"at_ms": 1000, "calibration_until_ms": 2000}
    hot = thermal_patch([85, 90], nonhuman=True, rect=[15, 25, 30, 35], **args)
    camera = coarse_cue("rgb", 0.95, zone="near", **args)
    radar = coarse_cue("radar", 0.95, zone="sector_a", **args)
    obstacle = depth_patch([1.5], nonhuman=True, rect=[55, 40, 20, 30], **args)
    other = dict(hot, sensor="thermal_aux", values=[20])
    specs = [
        ("daylight-presence", [camera, hot], {}),
        ("low-light-withdrawal", [camera, hot], {"lighting": "low_light"}),
        ("near-dark-active-depth", [obstacle], {"lighting": "near_dark"}),
        ("zero-visible-thermal", [hot], {"lighting": "zero_visible"}),
        (
            "radar-assisted-darkness",
            [hot, radar],
            {
                "lighting": "zero_visible",
                "zones": ["near", "sector_a"],
                "authorized_obstruction": True,
            },
        ),
        ("darkness-disagreement", [hot, other], {"lighting": "zero_visible"}),
        ("no-darkness-sensor", [camera], {"lighting": "zero_visible", "contract": "vehicle_stop"}),
        ("vehicle-obstacle-stop", [obstacle], {"contract": "vehicle_stop"}),
        ("drone-hover", [camera], {"contract": "drone_hover", "lighting": "zero_visible"}),
        ("drone-land-contract", [], {"contract": "drone_land"}),
        ("drone-retreat-contract", [hot], {"contract": "drone_retreat"}),
        ("stale-rectangle", [hot], {"now_ms": 1600}),
        ("thermal-saturated", [dict(hot, quality="saturated")], {"lighting": "zero_visible"}),
        ("cold-source", [dict(hot, values=[-5])], {"lighting": "zero_visible"}),
        ("fire-like-source", [dict(hot, values=[180])], {"lighting": "zero_visible"}),
    ]
    for name, observations, options in specs:
        params = {"now_ms": 1000, "evidence": "synthetic"}
        params.update(options)
        yield name, envelope(observations, **params)

    rgb = person_cue("rgb", 0.95, rect=[20, 20, 30, 50], **args)
    thermal = person_cue("thermal_person", 0.95, rect=[20, 20, 30, 50], **args)
    depth = person_cue("depth_person", 0.95, rect=[20, 20, 30, 50], **args)
    for name, obs, light in [
        ("person-daylight", [rgb, thermal], "daylight"),
        ("person-low-light-thermal", [rgb, thermal], "low_light"),
        ("person-near-dark-depth", [rgb, depth], "near_dark"),
        ("person-zero-visible-thermal", [rgb, thermal], "zero_visible"),
        ("person-all-support-lost", [rgb, dict(thermal, quality="dropped")], "zero_visible"),
        ("person-reentry-unlinked", [thermal], "zero_visible"),
    ]:
        yield (
            name,
            envelope(
                obs,
                now_ms=1000,
                evidence="synthetic",
                version=2,
                lighting=light,
                contract="vehicle_stop",
            ),
        )
    yield (
        "v2-through-obstruction-coarse",
        envelope(
            [radar],
            now_ms=1000,
            evidence="synthetic",
            version=2,
            mode="through_obstruction",
            zones=["sector_a"],
            authorized_obstruction=True,
            lighting="zero_visible",
        ),
    )


def run():
    for name, data in scenarios():
        print(json.dumps({"scenario": name, "result": evaluate(data)}, sort_keys=True))
