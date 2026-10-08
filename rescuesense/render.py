"""Original sensor-plane SVG view; only current direct-view geometry."""

import json
from html import escape

from .core import evaluate
from .schema import integer, parse, require


def render(data, now_ms):
    doc = parse(data)
    integer(now_ms)
    require(now_ms >= doc["now_ms"])
    doc["now_ms"] = now_ms
    result = evaluate(json.dumps(doc).encode())
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 660" role="img" aria-labelledby="title desc">',
        '<title id="title">RescueSense bounded sensor view</title>',
        '<desc id="desc">Coarse presence cues and expiring non-human rectangles. No camera image, identity or through-obstruction geometry.</desc>',
        '<rect width="1000" height="660" fill="#101f28"/>',
        '<g fill="#e8f1ed" font-family="monospace">',
        '<text x="30" y="42" font-size="25">RescueSense / bounded sensor view</text>',
        f'<text x="30" y="72">{escape(result["evidence"].upper())} · {escape(result["lighting"])} · no live hardware proof</text>',
        '<rect x="30" y="110" width="530" height="430" fill="#192f39" stroke="#607a82"/>',
        '<text x="46" y="138">Sensor plane · no imagery</text>',
    ]
    for i, c in enumerate(result["claims"]):
        # Sector-only displays use text. Never reconstruct positions of people.
        y = 113 + i * 27
        parts.append(
            f'<text x="580" y="{y}" font-size="12">{escape(c["zone"])} / {escape(c["capability"])}: {c["state"]}</text>'
        )
        if c["rect"] is not None and c["state"] == "PRESENT" and now_ms < c["valid_until_ms"]:
            x, y, w, h = c["rect"]
            expiry = (c["valid_until_ms"] - now_ms) / 1000
            label = f"{c['kind']} · {c['confidence']} uncalibrated · {'+'.join(c['sources'])}"
            parts.append(
                f'<g><set attributeName="visibility" to="hidden" begin="{expiry}s" fill="freeze"/>'
                f'<rect data-detection="{c["kind"]}" x="{30 + x * 5.3}" y="{110 + y * 4.3}" width="{w * 5.3}" height="{h * 4.3}" fill="none" stroke="#ffa861" stroke-width="3"/>'
                f'<text x="{30 + x * 5.3}" y="{102 + y * 4.3}" font-size="11">{escape(label)}</text></g>'
            )
    parts += [
        f'<text x="30" y="585" font-size="23">{result["recommendation"]["action"]} · recommendation only</text>',
        '<text x="30" y="613" font-size="13">UNKNOWN is not clearance. Rectangles expire; static snapshots are not live sensors.</text>',
        '<text x="30" y="638" font-size="13">No identity or tracking. Independent controller and authorization required.</text>',
        "</g></svg>",
    ]
    return "\n".join(parts)
