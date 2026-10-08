"""Administrator-local configuration, never accepted through the HTTP API."""

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from .contracts import Closed, Contract, Principal


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
    driver: Literal["replay", "file", "uvc", "rtsp"]
    address: str
    backend: Literal["ffmpeg", "v4l2", "avfoundation", "msmf"] = "ffmpeg"
    contract: Contract = "warn"
    lighting: Literal["daylight", "low_light", "near_dark", "zero_visible"] = "daylight"
    calibration_id: str = "unqualified"
    model: str | None = None
    provider: Literal["opencv", "coreml"] = "opencv"


class Credential(Closed):
    token_file: str
    principal: Principal


class ApplianceConfig(Closed):
    version: Literal[1]
    runtime_mode: Literal["appliance", "interactive"] = "appliance"
    host: Literal["127.0.0.1", "::1"] = "127.0.0.1"
    port: Annotated[int, Field(ge=1, le=65535)] = 8765
    profiles: Annotated[list[Profile], Field(min_length=1, max_length=4)]
    credentials: Annotated[list[Credential], Field(max_length=8)] = []
    integrity_bundle: str | None = None
    trust_root: str | None = None
    status_file: str


def load_config(path: Path) -> ApplianceConfig:
    with path.open("rb") as stream:
        config = ApplianceConfig.model_validate(strict_json(stream.read(65537)))
    if len({p.name for p in config.profiles}) != len(config.profiles):
        raise ValueError("invalid_request")
    for p in config.profiles:
        if p.driver in ("replay", "file"):
            p.address = str((path.parent / p.address).resolve())
        if p.model:
            p.model = str((path.parent / p.model).resolve())
    for c in config.credentials:
        c.token_file = str((path.parent / c.token_file).resolve())
    config.status_file = str((path.parent / config.status_file).resolve())
    return config
