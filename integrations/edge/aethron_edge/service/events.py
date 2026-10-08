import asyncio

from ..contracts import HealthEvent


def encode(event):
    data = event.model_dump_json(by_alias=True)
    if len(data.encode()) > 65536:
        raise ValueError("event_limit")
    return ("event: " + event.kind + "\ndata: " + data + "\n\n").encode()


async def stream(sessions, token, principal):
    yield encode(
        HealthEvent(
            api_version="1",
            scene_state="UNKNOWN",
            kind="gap",
            sequence=0,
            session=token,
            reason="stream_gap",
            retryable=True,
        )
    )
    while True:
        yield encode(sessions.snapshot(token, principal))
        await asyncio.sleep(0.05)
