"""Offline fixed-threshold PGM comparator; not a semantic or qualified detector."""

from bisect import insort

from ..temporal.pixels import decode_pgm


def detect_global_pgm(data):
    """v1: pixels<=127, eight-connected size3..1200, at most32 ordered proposals."""
    return detect_threshold_pgm(data, 127)


def detect_threshold_pgm(data, threshold):
    """Experimental scalar threshold; preserve the fixed global baseline's geometry."""
    if type(threshold) is not int or not 0 <= threshold <= 255:
        raise ValueError("invalid_threshold")
    width, height, pixels = decode_pgm(data)
    pending = bytearray(value <= threshold for value in pixels)
    components = []
    for seed in range(width * height):
        if not pending[seed]:
            continue
        pending[seed] = 0
        stack = [seed]
        size = 0
        left, top, right, bottom = width, height, 0, 0
        while stack:
            y, x = divmod(stack.pop(), width)
            size += 1
            left, top = min(left, x), min(top, y)
            right, bottom = max(right, x), max(bottom, y)
            for yy in range(max(0, y - 1), min(height, y + 2)):
                for xx in range(max(0, x - 1), min(width, x + 2)):
                    index = yy * width + xx
                    if pending[index]:
                        pending[index] = 0
                        stack.append(index)
        if 3 <= size <= 1200:
            # Keep the best32 after each component, with the same size/box ordering.
            insort(
                components,
                (
                    -size,
                    [
                        left / width,
                        top / height,
                        (right - left + 1) / width,
                        (bottom - top + 1) / height,
                    ],
                ),
            )
            if len(components) > 32:
                components.pop()
    return [
        {"class": "obstacle", "box": box, "score": 0.6, "variance": 0.0001, "range_m": None}
        for _, box in components
    ]
