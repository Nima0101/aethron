"""Original classical image baseline. Produces obstacle proposals, never semantic person/UAV labels."""

from array import array

from ..schema import require


def decode_pgm(data):
    require(type(data) is bytes and len(data) <= 640 * 512 + 64)
    parts = data.split(b"\n", 3)
    require(len(parts) == 4 and parts[0] == b"P5" and parts[2] == b"255")
    shape = parts[1].split()
    require(len(shape) == 2 and all(s.isdigit() and len(s) <= 3 for s in shape))
    w, h = (int(s) for s in shape)
    require(1 <= w <= 640 and 1 <= h <= 512 and len(parts[3]) == w * h)
    return w, h, parts[3]


def detect_pgm(data):
    w, h, pixels = decode_pgm(data)
    stride = w + 1
    integral = array("I", [0]) * ((h + 1) * stride)
    for y in range(h):
        row = 0
        for x in range(w):
            row += pixels[y * w + x]
            integral[(y + 1) * stride + x + 1] = integral[y * stride + x + 1] + row
    mask = bytearray(w * h)
    for y in range(h):
        top, bottom = max(0, y - 4), min(h, y + 5)
        for x in range(w):
            left, right = max(0, x - 4), min(w, x + 5)
            total = (
                integral[bottom * stride + right]
                - integral[top * stride + right]
                - integral[bottom * stride + left]
                + integral[top * stride + left]
            )
            if pixels[y * w + x] <= total / ((bottom - top) * (right - left)) - 20:
                mask[y * w + x] = 1
    components = []
    for index in range(w * h):
        if not mask[index]:
            continue
        mask[index] = 0
        stack = [index]
        count, left, right, top, bottom = 0, w, 0, h, 0
        while stack:
            p = stack.pop()
            y, x = divmod(p, w)
            count += 1
            left, right, top, bottom = min(left, x), max(right, x), min(top, y), max(bottom, y)
            for yy in range(max(0, y - 1), min(h, y + 2)):
                for xx in range(max(0, x - 1), min(w, x + 2)):
                    q = yy * w + xx
                    if mask[q]:
                        mask[q] = 0
                        stack.append(q)
        if 3 <= count <= 1200:
            components.append(
                (count, [left / w, top / h, (right - left + 1) / w, (bottom - top + 1) / h])
            )
    components.sort(key=lambda c: (-c[0], c[1]))
    return [
        {"class": "obstacle", "box": box, "score": 0.6, "variance": 0.0001, "range_m": None}
        for _, box in components[:32]
    ]
