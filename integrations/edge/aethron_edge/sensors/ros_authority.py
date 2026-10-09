"""Finite local software-clock authority, issued once per supervisor boot.

This opt-in path assumes a same-host publisher using system time. It cannot
prove sensor exposure timing, authenticate DDS publishers or synchronize remote
clocks. No persisted epoch or /clock simulation. Version 2 can explicitly
revalidate synthetic software bindings; it never renews a physical calibration.
Grants are private parent/worker IPC values, never accepted from HTTP or DDS.
"""

import secrets
import time
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import Field, model_validator

from ..config import strict_json
from .packets import Closed
from .provider import ProviderCalibration, _digest
from .registration import MAX_NS, _ns
from .ros2 import ClockMapping
from .ros2_node import _topic

MAX_SAMPLE_NS = 1_000_000
AUTHORITY_FAULTS = frozenset(
    {
        "authority_closed",
        "authority_expired",
        "clock_sample_invalid",
        "clock_rewind",
        "clock_drift",
        "renewal_rejected",
        "worker_fault",
        "source_clock_discontinuity",
        "sensor_invalid",
    }
)


class RosManifest(Closed):
    version: int = Field(ge=1, le=2)
    renewal: Literal["disabled", "software_fixture"] = "disabled"
    mode: Literal["ros"]
    timestamp_authority: Literal["same_host_system_software"]
    calibration: ProviderCalibration
    indices: tuple[tuple[int, int] | int, ...] = Field(min_length=1, max_length=64)
    valid_for_ns: int = Field(ge=1, le=600_000_000_000)
    timestamp_error_ns: int = Field(ge=0, le=49_000_000)
    clock_drift_budget_ns: int = Field(ge=0, le=49_000_000)
    topic: str
    camera_info_topic: str | None
    domain_id: int = Field(ge=0, le=232)
    meters_per_unit: float | None = Field(gt=0, le=1)

    @model_validator(mode="after")
    def configuration(self):
        if self.renewal != "disabled" and (
            self.version not in {2, 3} or self.calibration.rig.evidence != "synthetic"
        ):
            raise ValueError("unsupported_renewal")
        _topic(self.topic)
        if self.timestamp_error_ns + self.clock_drift_budget_ns + MAX_SAMPLE_NS > 50_000_000:
            raise ValueError("invalid_uncertainty")
        if len(set(self.indices)) != len(self.indices):
            raise ValueError("duplicate_sample")
        depth = self.calibration.modality == "depth"
        if depth:
            if self.meters_per_unit is None or self.camera_info_topic is None:
                raise ValueError("missing_depth_configuration")
            _topic(self.camera_info_topic)
            if self.camera_info_topic == self.topic or (
                self.calibration.lens is not None and self.version != 3
            ):
                raise ValueError("invalid_rectified_depth_configuration")
        elif self.meters_per_unit is not None or self.camera_info_topic is not None:
            raise ValueError("unexpected_camera_configuration")
        for index in self.indices:
            if depth:
                camera = self.calibration.source_camera
                if not isinstance(index, tuple) or not (
                    0 <= index[0] < camera.width and 0 <= index[1] < camera.height
                ):
                    raise ValueError("invalid_pixel")
            elif type(index) is not int or not 0 <= index < 4096:
                raise ValueError("invalid_point_index")
        return self

    @property
    def digest(self):
        return _digest(self.model_dump())


class RawDepthRosManifest(RosManifest):
    """Version 3 explicitly selects raw axial-depth images with a declared lens.

    Separate schema preserves version-1/2 serialized fields and digests. Topic
    content still requires installation evidence; metadata cannot prove it.
    """

    version: int = Field(ge=3, le=3)
    image_geometry: Literal["raw_distorted"]

    @model_validator(mode="after")
    def raw_depth_configuration(self):
        if self.calibration.modality != "depth" or self.calibration.lens is None:
            raise ValueError("raw_depth_lens_required")
        return self


def load_ros_manifest(raw):
    try:
        if type(raw) is not bytes:
            raise ValueError("invalid_bytes")
        value = strict_json(raw)
        if type(value) is not dict or type(value.get("version")) is not int:
            raise ValueError("invalid_version")
        schema = RawDepthRosManifest if value["version"] == 3 else RosManifest
        return schema.model_validate_json(raw)
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise ValueError("invalid_ros_manifest") from None


def _sample(monotonic, realtime):
    before = _ns(monotonic())
    wall = _ns(realtime())
    after = _ns(monotonic())
    if not 0 <= after - before <= MAX_SAMPLE_NS:
        raise ValueError("invalid_sample")
    # Midpoint rounding is included in the upward-rounded interval radius.
    return before, after, (before + after) // 2 - wall, (after - before + 1) // 2


@dataclass(frozen=True)
class BootGrant:
    boot_id: str
    manifest_digest: str
    issued_ns: int
    valid_until_ns: int
    offset_ns: int
    sample_error_ns: int
    generation: int = 0


def issue_boot_grant(manifest, *, monotonic=time.monotonic_ns, realtime=time.time_ns):
    try:
        if not isinstance(manifest, RosManifest):
            raise ValueError("invalid_manifest")
        before, after, offset, error = _sample(monotonic, realtime)
        deadline = before + manifest.valid_for_ns
        if deadline > MAX_NS or deadline <= after:
            raise ValueError("invalid_deadline")
        return BootGrant(secrets.token_hex(16), manifest.digest, before, deadline, offset, error)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("invalid_clock_authority") from None


class ClockGuard:
    """Thread-confined; drift/expiry revokes, it never silently remaps timestamps."""

    live_evidence = False

    def __init__(
        self, grant, manifest, *, boot_id, monotonic=time.monotonic_ns, realtime=time.time_ns
    ):
        self.closed = False
        self.fault = None
        self.monotonic = monotonic
        self.realtime = realtime
        try:
            if (
                not isinstance(grant, BootGrant)
                or not isinstance(manifest, RosManifest)
                or grant.boot_id != boot_id
                or grant.manifest_digest != manifest.digest
            ):
                raise ValueError("wrong_authority")
            self.grant = grant
            self.manifest = manifest
            self.boot_id = boot_id
            self.last_now = grant.issued_ns
            self.mapping = ClockMapping(
                domain="ros_system",
                offset_ns=grant.offset_ns,
                uncertainty_ns=(
                    manifest.timestamp_error_ns
                    + grant.sample_error_ns
                    + manifest.clock_drift_budget_ns
                ),
                valid_until_ns=grant.valid_until_ns,
            )
            if not self.check():
                raise ValueError("expired_authority")
        except (ValueError, TypeError, OverflowError):
            self.closed = True
            raise ValueError("invalid_clock_authority") from None

    def check(self, *, ingress=None, provider=None):
        if self.closed:
            self.close(ingress=ingress, provider=provider)
            return False
        try:
            before, after, offset, error = _sample(self.monotonic, self.realtime)
            if before < self.last_now:
                reason = "clock_rewind"
            elif after > self.grant.valid_until_ns:
                reason = "authority_expired"
            elif (
                abs(offset - self.grant.offset_ns) + error
                > self.manifest.clock_drift_budget_ns + self.grant.sample_error_ns
            ):
                reason = "clock_drift"
            else:
                reason = None
            if reason is not None:
                self.close(ingress=ingress, provider=provider, reason=reason)
                return False
            self.last_now = after
            return True
        except (ValueError, TypeError, OverflowError):
            self.close(ingress=ingress, provider=provider, reason="clock_sample_invalid")
            return False

    def close(self, *, ingress=None, provider=None, reason="authority_closed"):
        self.closed = True
        if self.fault is None:
            self.fault = reason if reason in AUTHORITY_FAULTS else "worker_fault"
        if ingress is not None:
            ingress.mapping = ingress.calibration = ingress.latest = None
            ingress.pending_break = True
            ingress.fault = "clock_authority_lost"
        if provider is not None:
            provider.close()

    def _successor(self, manifest, issued_ns):
        issued = _ns(issued_ns)
        deadline = issued + manifest.valid_for_ns
        if (
            manifest.digest != self.grant.manifest_digest
            or manifest.renewal != "software_fixture"
            or not self.grant.issued_ns + manifest.valid_for_ns // 2
            <= issued
            < self.grant.valid_until_ns
            or issued > self.last_now
            or deadline > MAX_NS
            or self.grant.generation >= MAX_NS
        ):
            raise ValueError("invalid_revalidation")
        return replace(
            self.grant,
            issued_ns=issued,
            valid_until_ns=deadline,
            generation=self.grant.generation + 1,
        )

    def _adopt(self, grant):
        self.grant = grant
        # Retain the original offset AND uncertainty; never accumulate allowed drift.
        self.mapping = self.mapping.model_copy(update={"valid_until_ns": grant.valid_until_ns})

    def renew(self, manifest, *, emitted_ns, expires_ns):
        """Parent only: rechecked manifest and fresh successful geometry are required."""
        try:
            if not self.check():
                raise ValueError("closed_authority")
            emitted, expires = _ns(emitted_ns), _ns(expires_ns)
            if (
                not 0 <= self.last_now - emitted <= 100_000_000
                or not self.last_now < expires <= self.grant.valid_until_ns
            ):
                raise ValueError("stale_geometry")
            grant = self._successor(manifest, self.last_now)
            self._adopt(grant)
            return grant
        except (ValueError, TypeError, AttributeError, OverflowError):
            self.close(reason="renewal_rejected")
            raise ValueError("invalid_authority_renewal") from None

    def accept_renewal(self, grant, manifest, *, ingress=None, provider=None):
        """Worker only: a sequential parent grant cannot revive a lost binding."""
        try:
            if not self.check() or not isinstance(grant, BootGrant):
                raise ValueError("closed_authority")
            _ns(grant.generation)
            _ns(grant.valid_until_ns)
            if grant != self._successor(manifest, grant.issued_ns):
                raise ValueError("wrong_successor")
            # Withdraw all old geometry/calibration before acquiring a new binding.
            if ingress is not None:
                ingress.mapping = ingress.calibration = ingress.latest = None
                ingress.pending_break = True
            if provider is not None:
                provider.close()
            self._adopt(grant)
        except (ValueError, TypeError, AttributeError, OverflowError):
            self.close(ingress=ingress, provider=provider, reason="renewal_rejected")
            raise ValueError("invalid_authority_renewal") from None


def read_ros_manifest(profile):
    from .provisioning import regular_file

    with regular_file(profile.sensor_manifest, 65536) as stream:
        manifest = load_ros_manifest(stream.read(65537))
    if manifest.topic != profile.address:
        raise ValueError("invalid_ros_manifest")
    return manifest
