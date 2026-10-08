"""Closed API v1 types; frozen v3 values are represented without reinterpretation."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Count = Annotated[int, Field(ge=0, le=2**53 - 1)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Unit = Annotated[Finite, Field(ge=0, le=1)]
Contract = Literal["warn", "vehicle_stop", "drone_hover", "drone_land", "drone_retreat"]
Modality = Literal["rgb", "lwir", "radar", "depth", "nir"]
ObjectClass = Literal[
    "person",
    "cyclist",
    "vehicle",
    "uav",
    "animal",
    "obstacle",
    "equipment",
    "hot",
    "cold",
    "fire_like",
    "smoke",
]
State = Literal["PRESENT", "UNKNOWN"]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Prediction(Closed):
    centre: Annotated[list[Unit], Field(min_length=2, max_length=2)]
    horizon_ms: Literal[200]
    evidence: Literal[False]


class Track(Closed):
    id: Annotated[str, Field(max_length=64)]
    class_: ObjectClass = Field(alias="class")
    box: Annotated[list[Unit], Field(min_length=4, max_length=4)]
    state: Literal["tentative", "observed", "coasting"]
    status: State
    score: Unit
    score_semantics: Literal["uncalibrated_support"]
    covariance: Annotated[list[Finite], Field(min_length=2, max_length=2)]
    freshness_ms: Count
    expires_at_ms: Count
    sources: Annotated[list[Modality], Field(max_length=5)]
    range_m: Annotated[Finite, Field(gt=0, le=500)] | None
    velocity_normalized_per_s: Annotated[list[Finite], Field(min_length=2, max_length=2)] | None
    direction_rad: Finite | None
    prediction: Prediction | None


class Recommendation(Closed):
    contract: Contract
    action: Literal["WARN", "STOP", "HOVER", "LAND", "RETREAT"]
    reason: Literal["hazard_or_unknown", "observe"]
    requires_independent_controller: Literal[True]


class V3Snapshot(Closed):
    version: Literal[3]
    at_ms: Count
    evidence: Literal["synthetic", "recorded", "external_unverified"] | None
    state: State
    tracks: Annotated[list[Track], Field(max_length=32)]
    reasons: Annotated[list[str], Field(max_length=128)]
    expires_at_ms: Count
    recommendation: Recommendation


class ReplayReport(Closed):
    api_version: Literal["1"]
    runtime_mode: Literal["replay"]
    frame_count: Annotated[int, Field(ge=1, le=300)]
    results: Annotated[list[V3Snapshot], Field(min_length=1, max_length=300)]


class Clock(Closed):
    domain: Literal["edge_monotonic"]
    emitted_ms: Count
    valid_for_ms: Annotated[int, Field(ge=0, le=100)]


class SceneEnvelope(Closed):
    api_version: Literal["1"]
    kind: Literal["scene"]
    sequence: Count
    session: Annotated[str, Field(pattern=r"^[a-f0-9]{32,64}$")]
    clock: Clock
    result: V3Snapshot


class HealthEvent(Closed):
    api_version: Literal["1"]
    kind: Literal["health", "gap"]
    sequence: Count
    session: str
    reason: Literal[
        "source_lost",
        "clock_untrusted",
        "calibration_expired",
        "model_error",
        "overload",
        "stream_gap",
        "closed",
    ]
    scene_state: Literal["UNKNOWN"]
    retryable: bool


class Error(Closed):
    api_version: Literal["1"]
    error: Literal[
        "invalid_request",
        "unauthorized",
        "forbidden",
        "capacity",
        "source_unavailable",
        "not_found",
    ]
    retryable: bool


class Capabilities(Closed):
    api_version: Literal["1"]
    core_version: Literal["0.2.0"]
    edge_version: Literal["0.1.0"]
    protocol: Literal[3]
    runtime_mode: Literal["appliance", "interactive", "replay"]
    drivers: list[str]
    provider: str
    qualification_refs: list[str]


class Principal(Closed):
    name: Annotated[str, Field(pattern=r"^[a-z0-9-]{1,48}$")]
    scopes: list[Literal["observe", "session:manage"]]


class SessionRequest(Closed):
    source_profile: Annotated[str, Field(pattern=r"^[a-z0-9-]{1,48}$")]
    contract: Contract


class SessionHandle(Closed):
    session: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
    source_profile: str
