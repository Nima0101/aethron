"""Guest-only raw sensor diagnostics; no frame storage or semantic claims.

At most four profiles are retained, but aggregate counters grow with the run.
Trusted callers supply mappings and monotonic integer milliseconds in one clock
domain. This observer does not authenticate status or validate its host clock.
``processing_at_end`` means progress was reported within the inclusive preceding
2000 ms; a later fault, stalled counter or invalid sample does not clear that
recent-activity window. Recovery/update flags retain historical observations.
These fields do not establish continuous availability or current device health.
"""

import re


def count(value):
    return type(value) is int and 0 <= value <= 2**53 - 1


class SensorEvidence:
    def __init__(self, profiles):
        if not isinstance(profiles, dict) or len(profiles) > 4:
            raise ValueError("invalid_probe_profiles")
        if any(
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z0-9-]{1,48}", name)
            or evidence not in {"recorded", "external_unverified"}
            for name, evidence in profiles.items()
        ):
            raise ValueError("invalid_probe_profiles")
        self.profiles = dict(profiles)
        self.rows = {
            name: {
                "source_evidence": evidence,
                "batches_observed": 0,
                "processing_observed": False,
                "processing_resumed_after_fault": False,
                "updated_runtime_processing": False,
                "unavailable_samples": 0,
                "fault_samples": 0,
                "invalid_samples": 0,
            }
            for name, evidence in profiles.items()
        }
        self.previous = dict.fromkeys(profiles, 0)
        self.last_emitted = dict.fromkeys(profiles, -1)
        self.last_activity = dict.fromkeys(profiles, None)
        self.now_ms = 0
        self.fault_counts = None
        self.update_started = None

    def observe(self, status, now_ms):
        self.now_ms = now_ms
        emitted = status.get("emitted_ms")
        expires = status.get("status_expires_ms")
        valid = (
            count(emitted)
            and count(expires)
            and emitted <= now_ms <= expires <= emitted + 2000
            and status.get("scene_state") == "UNKNOWN"
            and status.get("qualified") is False
            and (self.update_started is None or emitted >= self.update_started)
        )
        sensors = status.get("sensors", {})
        for name, row in self.rows.items():
            sensor = sensors.get(name) if isinstance(sensors, dict) else None
            if (
                not valid
                or not isinstance(sensor, dict)
                or not count(sensor.get("batches"))
                or sensor.get("source_evidence") != self.profiles[name]
                or sensor.get("qualified") is not False
                or type(sensor.get("available")) is not bool
                or emitted <= self.last_emitted[name]
                or sensor["batches"] < self.previous[name]
            ):
                row["invalid_samples"] += 1
                continue
            self.last_emitted[name] = emitted
            row["unavailable_samples"] += not sensor["available"]
            row["fault_samples"] += sensor.get("state") == "fault"
            batches = sensor["batches"]
            advanced = batches > self.previous[name]
            row["batches_observed"] += batches - self.previous[name]
            self.previous[name] = batches
            current = sensor["available"] and sensor.get("state") == "processing"
            if current and advanced:
                row["processing_observed"] = True
                self.last_activity[name] = emitted
                if self.fault_counts is not None and self.update_started is None:
                    if batches > self.fault_counts[name] + 10:
                        row["processing_resumed_after_fault"] = True
                if self.update_started is not None and batches > 10:
                    row["updated_runtime_processing"] = True

    def mark_fault(self):
        self.fault_counts = dict(self.previous)

    def mark_update(self, started_ms):
        self.update_started = started_ms
        self.previous = dict.fromkeys(self.profiles, 0)

    def recovered(self):
        return all(row["processing_resumed_after_fault"] for row in self.rows.values())

    def updated(self):
        return all(row["updated_runtime_processing"] for row in self.rows.values())

    def result(self, now_ms=None):
        now_ms = self.now_ms if now_ms is None else now_ms
        return {
            name: dict(
                row,
                processing_at_end=self.last_activity[name] is not None
                and 0 <= now_ms - self.last_activity[name] <= 2000,
            )
            for name, row in self.rows.items()
        }
