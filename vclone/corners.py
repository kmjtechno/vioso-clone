"""Safe four-corner geometry for the independent calibration editor.

Input order is top-left, top-right, bottom-right, bottom-left in camera
image coordinates (Y increases downward). No native VIOSO format assumed.
"""
from __future__ import annotations

from math import isfinite

MAX_IMAGE_PIXELS = 4096 * 2160


def validate_size(size, *, max_width=4096, max_height=2160):
    if (not isinstance(size, (tuple, list)) or len(size) != 2
            or any(type(v) is not int for v in size)):
        raise ValueError("image size must be a pair of integer dimensions")
    width, height = size
    if (width < 2 or height < 2 or width > max_width or height > max_height
            or width * height > MAX_IMAGE_PIXELS):
        raise ValueError("image dimensions exceed editor safety bounds")
    return width, height


def validate_corners(points, image_size, *, min_area_fraction=0.005):
    """Return validated float coordinates, or reject misleading geometry.

    Four convex corners must be clicked in clockwise screen order:
    TL -> TR -> BR -> BL. Area gates prevent thin/degenerate quadrilaterals.
    """
    width, height = validate_size(image_size)
    if (type(min_area_fraction) not in (float, int)
            or not isfinite(min_area_fraction)
            or not 0 < min_area_fraction <= 0.25):
        raise ValueError("invalid corner area threshold")
    if not isinstance(points, (list, tuple)) or len(points) != 4:
        raise ValueError("select exactly four corners: TL, TR, BR, BL")
    coords = []
    for point in points:
        if (not isinstance(point, (tuple, list)) or len(point) != 2
                or any(type(c) not in (int, float) for c in point)):
            raise ValueError("corner positions must be finite coordinate pairs")
        x, y = point
        if (not isfinite(x) or not isfinite(y)
                or x < 0 or y < 0 or x > width - 1 or y > height - 1):
            raise ValueError("corner lies outside the camera image")
        coords.append([float(x), float(y)])

    signs = []
    for i in range(4):
        a, b, c = coords[i], coords[(i + 1) % 4], coords[(i + 2) % 4]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        signs.append(cross)
    if min(signs) <= 1e-9:
        raise ValueError("corners must form a convex TL-TR-BR-BL quadrilateral")

    area2 = sum(
        coords[i][0] * coords[(i + 1) % 4][1]
        - coords[(i + 1) % 4][0] * coords[i][1]
        for i in range(4)
    )
    area = area2 / 2
    if area < float(min_area_fraction) * (width - 1) * (height - 1):
        raise ValueError("camera quadrilateral is too small for reliable calibration")

    # Consistent TL/TR/BR/BL labelling, even under perspective distortion.
    top = coords[0][1] + coords[1][1]
    bottom = coords[2][1] + coords[3][1]
    left = coords[0][0] + coords[3][0]
    right = coords[1][0] + coords[2][0]
    if not (top < bottom and left < right):
        raise ValueError("select corners in TL, TR, BR, BL image order")
    return coords


def content_corners(size):
    width, height = validate_size(size)
    return [[0.0, 0.0], [float(width - 1), 0.0],
            [float(width - 1), float(height - 1)], [0.0, float(height - 1)]]
