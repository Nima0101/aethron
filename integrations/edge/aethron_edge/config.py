"""Administrator-local configuration, never accepted through the HTTP API."""

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .common_types import Closed, Contract, Principal


def strict_json(data: bytes, limit=65536):
    if len(data) > limit:
        raise ValueError("invalid_request")

    def pairs(items):
        value = {}
        for k, v in items:
            if k in value:
                raise ValueError("invalid_request")
            value[k] = v
        return value

    def invalid(value):
        raise ValueError("invalid_request")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


class Profile(Closed):
    name: Annotated[str, Field(pattern=r"^[a-z0-9-]{1,48}$")]
    driver: Literal["replay", "file", "uvc", "rtsp", "sensor-replay", "sensor-ros"]
    address: str
    backend: Literal["ffmpeg", "v4l2", "avfoundation", "msmf"] = "ffmpeg"
    contract: Contract = "warn"
    lighting: Literal["daylight", "low_light", "near_dark", "zero_visible"] = "daylight"
    calibration_id: str = "unqualified"
    sensor_manifest: str | None = None
    model: str | None = None
    provider: Literal["opencv", "coreml"] = "opencv"

    @model_validator(mode="after")
    def sensor_configuration(self):
        if self.driver in {"sensor-replay", "sensor-ros"}:
            if not self.sensor_manifest or self.model is not None:
                raise ValueError("invalid_sensor_configuration")
        elif self.sensor_manifest is not None:
            raise ValueError("unexpected_sensor_manifest")
        return self


class Credential(Closed):
    token_file: str
    principal: Principal


class TelemetryConfiguration(Closed):
    name: Annotated[str, Field(pattern=r"^[a-z0-9-]{1,48}$")]
    system_id: Annotated[int, Field(ge=1, le=255)]
    component_id: Annotated[int, Field(ge=1, le=255)]
    port: Annotated[int, Field(ge=1, le=65535)]
    credential_file: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    clock_policy_file: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    replay_file: Annotated[str, Field(min_length=1, max_length=4096)]

    @model_validator(mode="after")
    def authority_source(self):
        if (self.credential_file is None) == (self.clock_policy_file is None):
            raise ValueError("exactly_one_telemetry_authority_required")
        return self


class ApplianceConfig(Closed):
    version: Literal[1]
    runtime_mode: Literal["appliance", "interactive"] = "appliance"
    host: Literal["127.0.0.1", "::1"] = "127.0.0.1"
    port: Annotated[int, Field(ge=1, le=65535)] = 8765
    profiles: Annotated[list[Profile], Field(min_length=1, max_length=4)]
    credentials: Annotated[list[Credential], Field(max_length=8)] = []
    telemetry: Annotated[list[TelemetryConfiguration], Field(max_length=2)] = []
    integrity_bundle: str | None = None
    trust_root: str | None = None
    status_file: str

    @model_validator(mode="after")
    def telemetry_configuration(self):
        if len({p.name for p in self.telemetry}) != len(self.telemetry) or len(
            {p.port for p in self.telemetry}
        ) != len(self.telemetry):
            raise ValueError("duplicate_telemetry_configuration")
        return self


def load_config(path: Path) -> ApplianceConfig:
    with path.open("rb") as stream:
        config = ApplianceConfig.model_validate(strict_json(stream.read(65537)))
    if len({p.name for p in config.profiles}) != len(config.profiles):
        raise ValueError("invalid_request")
    for p in config.profiles:
        if p.driver == "sensor-ros" and (path.parent / p.sensor_manifest).is_symlink():
            raise ValueError("invalid_sensor_configuration")
        if p.driver == "sensor-replay" and any(
            (path.parent / value).is_symlink() for value in (p.address, p.sensor_manifest)
        ):
            raise ValueError("invalid_sensor_configuration")
        if p.driver in ("replay", "file", "sensor-replay"):
            p.address = str((path.parent / p.address).resolve())
        if p.sensor_manifest:
            p.sensor_manifest = str((path.parent / p.sensor_manifest).resolve())
        if p.model:
            p.model = str((path.parent / p.model).resolve())
    for c in config.credentials:
        c.token_file = str((path.parent / c.token_file).resolve())
    for p in config.telemetry:
        # Do not resolve away symlinks before the private credential/journal
        # loaders apply their own descriptor-based checks.
        for name in ("credential_file", "clock_policy_file"):
            value = getattr(p, name)
            if value is not None:
                setattr(p, name, str((path.parent / value).absolute()))
        p.replay_file = str((path.parent / p.replay_file).absolute())
    for field in ("integrity_bundle", "trust_root"):
        value = getattr(config, field)
        if value:
            setattr(config, field, str((path.parent / value).resolve()))
    config.status_file = str((path.parent / config.status_file).resolve())
    return config
