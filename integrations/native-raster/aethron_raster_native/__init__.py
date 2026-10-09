"""Explicit optional C++20 recorded Brown remapping; Python remains the default."""

from aethron_edge.sensors.packets import Raster, decode_image
from aethron_edge.sensors.raster_rectification import (
    MAX_OUTPUT_PIXELS,
    RectifiedMono8,
    RectifiedMono16,
)
from aethron_edge.sensors.rectification import LensCalibration

from . import _kernel


def rectify_recorded(frame, lens):
    """Return byte/mask-compatible recorded counts; no provenance or live grant."""
    try:
        if type(frame) is not Raster or type(lens) is not LensCalibration:
            raise ValueError("unsupported_input")
        lens = LensCalibration.model_validate(lens.model_dump())
        frame = decode_image(frame.layout.model_dump(), frame.data)
        layout, c, out = frame.layout, lens.camera, lens.output_camera
        if (
            layout.encoding not in {"mono8", "mono16"}
            or (layout.width, layout.height) != (c.width, c.height)
            or out.width * out.height > MAX_OUTPUT_PIXELS
        ):
            raise ValueError("raster_contract")
        data, mask = _kernel.remap(
            frame.data,
            (
                c.width,
                c.height,
                layout.step,
                layout.bytes_per_pixel,
                int(layout.is_bigendian),
                out.width,
                out.height,
            ),
            (
                c.fx,
                c.fy,
                c.cx,
                c.cy,
                out.fx,
                out.fy,
                out.cx,
                out.cy,
                lens.valid_radius,
                *lens.distortion,
            ),
        )
        result = RectifiedMono8 if layout.encoding == "mono8" else RectifiedMono16
        return result(out.width, out.height, layout.modality, data, mask)
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError("invalid_raster_rectification") from None
