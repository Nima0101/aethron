"""Shared strict types for local configuration and API, without HTTP schemas."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Contract = Literal["warn", "vehicle_stop", "drone_hover", "drone_land", "drone_retreat"]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Principal(Closed):
    name: Annotated[str, Field(pattern=r"^[a-z0-9-]{1,48}$")]
    scopes: list[Literal["observe", "session:manage"]]
