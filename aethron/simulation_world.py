"""Synthetic aggregate composition of P6 world admission and P5 recommendations."""

import json

from .schema import parse, require
from .simulated_safety import DefensiveSimulation
from .world import CLOCK_DOMAIN, WorldModel


class SimulatedWorld:
    """Serialized, memory-only simulation stream; no track export or actuation."""

    def __init__(self, contract):
        self._defensive = DefensiveSimulation(contract)
        self._contract = contract
        self._world = WorldModel()

    @staticmethod
    def _output(world, recommendation):
        return {
            "simulation_world_version": 1,
            "quarantined": world["quarantined"],
            "diagnostics": list(world["scene"]["reasons"]),
            "recommendation": recommendation,
        }

    def step(self, data, *, now_ms, coordinate_frame, clock_domain):
        try:
            f = parse(data)
            require(f["version"] == 3)
            require(f["evidence"] == "synthetic" and f["contract"] == self._contract)
        except ValueError:
            # Do not let unsupported evidence enter temporal state, even briefly.
            data = b""
        world = self._world.step(
            data, now_ms=now_ms, coordinate_frame=coordinate_frame, clock_domain=clock_domain
        )
        aggregate = b""
        if not world["quarantined"]:
            scene = world["scene"]
            aggregate = json.dumps(
                {
                    "version": 1,
                    "at_ms": f["at_ms"],
                    "expires_at_ms": min(f["at_ms"] + 100, scene["expires_at_ms"]),
                    "evidence": "synthetic",
                    "state": scene["state"],
                    "clock_domain": CLOCK_DOMAIN,
                },
                allow_nan=False,
                separators=(",", ":"),
            ).encode("ascii")
        return self._output(world, self._defensive.step(aggregate, now_ms=now_ms))

    def watchdog(self, *, now_ms):
        world = self._world.watchdog(now_ms=now_ms)
        return self._output(world, self._defensive.watchdog(now_ms=now_ms))

    def close(self):
        self._world.close()
        self._defensive.close()
