"""Bounded static synthetic-grid route search; never an actuator interface."""

import json
from collections import deque

from ._json_bounds import check as check_bounds
from .schema import keys, require, unique_pairs
from .simulated_plan import SimulationPlan, _parse


def _request(data):
    require(type(data) is bytes and len(data) <= 8192 and check_bounds(data))
    try:
        obj = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _: require(False),
        )
        keys(
            obj,
            "version at_ms expires_at_ms evidence coordinate_frame clock_domain grid start goal",
        )
        obj["path"] = [obj.pop("start"), obj.pop("goal")]
        # Reuse the exact P7 bounds before indexing or starting the search.
        return _parse(json.dumps(obj).encode("ascii"))
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_input") from None


def _search(grid, start, goal):
    if grid[start[1]][start[0]] != "free" or grid[goal[1]][goal[0]] != "free":
        return [], "endpoint_not_free"
    parents = {start: None}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if cell == goal:
            path = []
            while cell is not None:
                path.append(list(cell))
                cell = parents[cell]
            if len(path) > 64:
                return [], "path_limit"
            return path[::-1], None
        x, y = cell
        for nx, ny in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
            neighbor = (nx, ny)
            if (
                0 <= ny < len(grid)
                and 0 <= nx < len(grid[0])
                and grid[ny][nx] == "free"
                and neighbor not in parents
            ):
                parents[neighbor] = cell
                queue.append(neighbor)
    return [], "unreachable"


class SimulationRoute:
    """One serialized simulation stream; no retained map, route or identifiers."""

    def __init__(self, contract):
        self._plan = SimulationPlan(contract)
        self._reasons = ()

    def _output(self, assessment, path=(), reason=None):
        reasons = set(assessment["reasons"])
        if reason:
            reasons.add(reason)
        if not assessment["input_accepted"]:
            reasons.update(self._reasons)
        self._reasons = tuple(sorted(reasons))
        found = bool(path) and assessment["plan_admissible"] and not reasons
        return {
            "simulation_route_version": 1,
            "route_found": found,
            "path": path if found else [],
            "reasons": sorted(reasons),
            "recommendation": assessment["recommendation"],
        }

    def step(self, data, *, now_ms):
        try:
            obj = _request(data)
        except ValueError:
            return self._output(self._plan.step(b"", now_ms=now_ms))
        start, goal = (tuple(p) for p in obj["path"])
        path, reason = _search(obj["grid"], start, goal)
        obj["path"] = path or [list(start)]
        assessment = self._plan.step(json.dumps(obj).encode("ascii"), now_ms=now_ms)
        return self._output(assessment, path, reason)

    def watchdog(self, *, now_ms):
        return self._output(self._plan.watchdog(now_ms=now_ms))

    def close(self):
        self._plan.close()
        self._reasons = ("closed",)
