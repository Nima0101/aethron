"""Original background block registration; no identity features or durable image state."""

from .math import translation
from .pixels import decode_pgm


def estimate_translation(previous, current):
    w, h, a = decode_pgm(previous)
    ww, hh, b = decode_pgm(current)
    invalid = {"dx": 0.0, "dy": 0.0, "variance": 0.05, "valid": False}
    if (w, h) != (ww, hh) or w < 100 or h < 100:
        return invalid
    sw, sh = w // 4, h // 4
    a = [a[y * 4 * w + x * 4] for y in range(sh) for x in range(sw)]
    b = [b[y * 4 * w + x * 4] for y in range(sh) for x in range(sw)]
    samples = []
    locations = []
    for gy in range(1, 5):
        for gx in range(1, 7):
            x, y = gx * sw // 7, gy * sh // 5
            if min(x, y) < 7 or x + 7 >= sw or y + 7 >= sh:
                continue
            patch = [a[(y + dy) * sw + x + dx] for dy in range(-3, 4) for dx in range(-3, 4)]
            mean = sum(patch) / 49
            if sum((v - mean) ** 2 for v in patch) / 49 < 25:
                continue
            candidates = []
            for sy in range(-4, 5):
                for sx in range(-4, 5):
                    error = (
                        sum(
                            abs(patch[(dy + 3) * 7 + dx + 3] - b[(y + sy + dy) * sw + x + sx + dx])
                            for dy in range(-3, 4)
                            for dx in range(-3, 4)
                        )
                        / 49
                    )
                    candidates.append((error, sx, sy))
            candidates.sort()
            best = candidates[0]
            if best[0] <= 20 and candidates[1][0] - best[0] >= 0.5:
                samples.append([best[1] * 4 / w, best[2] * 4 / h])
                locations.append((gx, gy))
    spread = len({p[0] for p in locations}) >= 3 and len({p[1] for p in locations}) >= 2
    return translation(samples, spatially_distributed=spread)
