"""Bounded supplied-path checks for static synthetic grids; no motion authority."""

import json

from ._json_bounds import check as check_bounds
from .schema import enum, integer, keys, require, unique_pairs
from .simulated_safety import DefensiveSimulation


def _parse(data):
    require(type(data) is bytes and len(data) <= 8192 and check_bounds(data))
    try:
        obj = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _: require(False),
        )
        keys(obj, "version at_ms expires_at_ms evidence coordinate_frame clock_domain grid path")
        integer(obj["version"], 1, 1)
        integer(obj["at_ms"])
        integer(obj["expires_at_ms"])
        enum(obj["evidence"], ("synthetic",))
        enum(obj["coordinate_frame"], ("synthetic_grid",))
        enum(obj["clock_domain"], ("host_monotonic_ms",))
        grid, path = obj["grid"], obj["path"]
        require(type(grid) is list and 1 <= len(grid) <= 16)
        require(type(grid[0]) is list and 1 <= len(grid[0]) <= 16)
        width = len(grid[0])
        for row in grid:
            require(type(row) is list and len(row) == width)
            for cell in row:
                enum(cell, ("free", "blocked", "unknown"))
        require(type(path) is list and 1 <= len(path) <= 64)
        for cell in path:
            require(type(cell) is list and len(cell) == 2)
            integer(cell[0], 0, width - 1)
            integer(cell[1], 0, len(grid) - 1)
        return obj
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("invalid_input") from None


class SimulationPlan:
    """One synthetic stream, retaining P5 watermarks and fixed diagnostics only."""

    def __init__(self, contract):
        self._defensive = DefensiveSimulation(contract)
        self._reasons = ()

    def _output(self, rec, reasons=()):
        reasons = set(reasons).union(rec["reasons"])
        if rec["accepted"] and rec["at_ms"] >= rec["expires_at_ms"]:
            reasons.add("expired_snapshot")
        if not rec["accepted"]:
            reasons.update(self._reasons)
        self._reasons = tuple(sorted(reasons))
        return {
            "simulation_plan_version": 1,
            "input_accepted": rec["accepted"],
            "plan_admissible": rec["accepted"] and not reasons,
            "reasons": sorted(reasons),
            "recommendation": rec,
        }

    def step(self, data, *, now_ms):
        try:
            obj = _parse(data)
        except ValueError:
            return self._output(self._defensive.step(b"", now_ms=now_ms))
        declaration = {
            k: obj[k] for k in ("version", "at_ms", "expires_at_ms", "evidence", "clock_domain")
        }
        declaration["state"] = "UNKNOWN"
        rec = self._defensive.step(json.dumps(declaration).encode("ascii"), now_ms=now_ms)
        if not rec["accepted"]:
            return self._output(rec)
        reasons = set()
        previous = None
        for x, y in obj["path"]:
            cell = obj["grid"][y][x]
            if cell != "free":
                reasons.add("blocked_cell" if cell == "blocked" else "unknown_cell")
            if previous is not None and abs(x - previous[0]) + abs(y - previous[1]) > 1:
                reasons.add("nonadjacent_step")
            previous = (x, y)
        return self._output(rec, reasons)

    def watchdog(self, *, now_ms):
        return self._output(self._defensive.watchdog(now_ms=now_ms))

    def close(self):
        self._defensive.close()
        self._reasons = ("closed",)
