"""Memory-only scene state with bounded lifetime and explicit sensor-loss watchdog."""

import math
import secrets

from ..actions import recommend
from ..schema import integer, parse, require
from .fusion import observations
from .math import Axis, assignment, centre, iou


class Track:
    def __init__(self, ordinal, d, at):
        self.ordinal = ordinal
        self.kind = d["class"]
        x, y = centre(d["box"])
        self.axes = [Axis(x, d["variance"]), Axis(y, d["variance"])]
        self.box = list(d["box"])
        self.born = at
        self.last = d["at_ms"]
        self.hits = 1
        self.support = d
        self.observed = True

    def predicted_box(self):
        return [
            self.axes[0].x - self.box[2] / 2,
            self.axes[1].x - self.box[3] / 2,
            self.box[2],
            self.box[3],
        ]


class Session:
    """Call step with trusted monotonic now_ms, watchdog on acquisition stall, close on exit.

    No public state serializer, caller-defined session ID, re-ID store or disk writer.
    Replay canonicalization is outside this API; live tokens always use system randomness.
    """

    def __init__(self):
        self._tracks = []
        self._serial = 0
        self._token = secrets.token_hex(12)
        self._last = self._start = None
        self._evidence = None
        self._contract = "warn"
        self._ego_valid = False
        self._closed = False

    def _reset(self):
        self._tracks.clear()
        self._serial = 0
        self._token = secrets.token_hex(12)
        self._last = self._start = None
        self._ego_valid = False

    def close(self):
        self._reset()
        self._evidence = None
        self._closed = True

    def step(self, data, *, now_ms):
        try:
            require(not self._closed)
            integer(now_ms)
            f = parse(data)
            require(f["version"] == 3)
            at = f["at_ms"]
            require(0 <= now_ms - at <= 100)
            require(self._last is None or at > self._last)
            self._contract = f["contract"]
            if (
                f["scene_break"]
                or not f["ego"]["valid"]
                or (self._start is not None and at - self._start >= 30000)
                or (self._last is not None and at - self._last > 1000)
                or (self._evidence is not None and self._evidence != f["evidence"])
            ):
                self._reset()
            self._evidence = f["evidence"]
            self._ego_valid = f["ego"]["valid"]
            if self._start is None:
                self._start = at
            dt = (at - self._last) / 1000 if self._last is not None else 0
            self._expire(now_ms)
            for t in self._tracks:
                t.observed = False
                for axis, shift in zip(t.axes, (f["ego"]["dx"], f["ego"]["dy"])):
                    axis.predict(dt, shift, f["ego"]["variance"])
            self._tracks = [t for t in self._tracks if all(0 <= ax.x <= 1 for ax in t.axes)]
            ds, reasons = observations(f, now_ms)
            if not self._ego_valid:
                reasons.append("ego_unknown")
            self._associate(ds, at, reasons)
            self._last = at
            return self._output(now_ms, reasons)
        except (ValueError, KeyError):
            self._reset()
            return self._output(
                now_ms if type(now_ms) is int and now_ms >= 0 else 0, ["invalid_input"]
            )

    def _expire(self, now):
        self._tracks = [
            t for t in self._tracks if 0 <= now - t.last <= 500 and now - t.born < 10000
        ]

    def watchdog(self, *, now_ms):
        integer(now_ms)
        if self._last is not None and now_ms < self._last:
            self._reset()
            return self._output(now_ms, ["clock_regression"])
        self._expire(now_ms)
        for t in self._tracks:
            t.observed = False
        return self._output(now_ms, ["acquisition_stalled"])

    def _associate(self, ds, at, reasons):
        n, m = len(self._tracks), len(ds)
        costs = []
        centres = [centre(d["box"]) for d in ds]
        for t in self._tracks:
            row = []
            ax, ay = t.axes
            predicted = t.predicted_box()
            for d, (x, y) in zip(ds, centres):
                if t.kind != d["class"]:
                    row.append(1000.0)
                    continue
                rx, ry = x - ax.x, y - ay.x
                distance = math.hypot(rx, ry)
                if distance > 0.2:
                    row.append(1000.0)
                    continue
                mahal = rx * rx / (ax.a + d["variance"]) + ry * ry / (ay.a + d["variance"])
                row.append(
                    distance / 0.2 + 0.4 * (1 - iou(predicted, d["box"])) if mahal <= 25 else 1000.0
                )
            costs.append(row + [1.5] * n)
        matched, blocked = set(), set()
        for i, j in assignment(costs):
            if j >= m or costs[i][j] >= 1.5:
                continue
            alternatives = [costs[i][k] for k in range(m) if k != j]
            alternatives += [costs[k][j] for k in range(n) if k != i]
            if any(abs(c - costs[i][j]) < 0.05 for c in alternatives):
                reasons.append("association_ambiguous")
                blocked.add(j)
                blocked.update(k for k in range(m) if costs[i][k] < 1.5)
                continue
            t, d = self._tracks[i], ds[j]
            for ax, z in zip(t.axes, centre(d["box"])):
                ax.update(z, d["variance"])
            t.box = list(d["box"])
            t.last = d["at_ms"]
            t.hits += 1
            t.support = d
            t.observed = True
            matched.add(j)
        for j, d in enumerate(ds):
            if j in matched or j in blocked or d["score"] < 0.6:
                continue
            if len(self._tracks) >= 32:
                reasons.append("capacity")
                break
            self._serial += 1
            self._tracks.append(Track(self._serial, d, at))

    def _output(self, now, reasons):
        tracks = []
        for t in self._tracks:
            observed = t.observed and now <= t.support["until_ms"]
            state = ("observed" if t.hits >= 2 else "tentative") if observed else "coasting"
            box = t.box if observed else t.predicted_box()
            if any(v < 0 for v in box) or box[0] + box[2] > 1 or box[1] + box[3] > 1:
                continue
            motion_valid = self._ego_valid and t.hits >= 2
            velocity = [round(a.v, 6) for a in t.axes] if motion_valid else None
            prediction = [round(a.x + a.v * 0.2, 6) for a in t.axes] if motion_valid else None
            if prediction and not all(0 <= v <= 1 for v in prediction):
                prediction = None
            tracks.append(
                {
                    "id": self._token + ":" + str(t.ordinal),
                    "class": t.kind,
                    "box": list(box),
                    "state": state,
                    "status": "PRESENT" if observed else "UNKNOWN",
                    "score": round(
                        t.support["score"]
                        if observed
                        else t.support["score"] * max(0, 1 - (now - t.last) / 500),
                        6,
                    ),
                    "score_semantics": "uncalibrated_support",
                    "covariance": [round(a.a, 9) for a in t.axes],
                    "freshness_ms": now - t.support["at_ms"],
                    "expires_at_ms": min(
                        now + 200,
                        t.last + 500,
                        t.born + 10000,
                        t.support["until_ms"] if observed else now + 200,
                    ),
                    "sources": list(t.support["sources"]) if observed else [],
                    "range_m": t.support["range_m"] if observed else None,
                    "velocity_normalized_per_s": velocity,
                    "direction_rad": round(math.atan2(velocity[1], velocity[0]), 6)
                    if velocity and math.hypot(*velocity) > 1e-6
                    else None,
                    "prediction": {"centre": prediction, "horizon_ms": 200, "evidence": False}
                    if prediction
                    else None,
                }
            )
        present = any(t["status"] == "PRESENT" for t in tracks)
        return {
            "version": 3,
            "at_ms": now,
            "evidence": self._evidence,
            "state": "PRESENT" if present else "UNKNOWN",
            "tracks": tracks,
            "reasons": sorted(set(reasons)),
            "expires_at_ms": min([now + 200] + [t["expires_at_ms"] for t in tracks]),
            "recommendation": recommend(self._contract, [{"state": "UNKNOWN"}]),
        }
