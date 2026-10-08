"""One atomic bounded slot: a killed writer cannot block the watchdog reader."""

import json
import queue


class Mailbox:
    def __init__(self, context):
        self.slot = context.RawArray("B", 65536)
        self.length = context.RawValue("i", 0)
        self.lock = context.Lock()

    def put_nowait(self, message):
        value = dict(message)
        if isinstance(value.get("data"), bytes):
            value["data"] = value["data"].decode("utf-8")
        data = json.dumps(value, allow_nan=False, separators=(",", ":")).encode()
        if len(data) > 65536:
            raise ValueError("message_limit")
        if not self.lock.acquire(False):
            raise queue.Full()
        try:
            memoryview(self.slot).cast("B")[: len(data)] = data
            self.length.value = len(data)
        finally:
            self.lock.release()

    def get_nowait(self):
        if not self.lock.acquire(False):
            raise queue.Empty()
        try:
            if not self.length.value:
                raise queue.Empty()
            data = bytes(memoryview(self.slot).cast("B")[: self.length.value])
            self.length.value = 0
        finally:
            self.lock.release()
        value = json.loads(data)
        if isinstance(value.get("data"), str):
            value["data"] = value["data"].encode()
        return value
