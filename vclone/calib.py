"""Calibration engine: Gray-code scan, camera<->projector map, warp mesh, edge blend.

Clean-room design; operates on arrays so it is testable without hardware.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


def _nbits(n: int) -> int:
    return max(1, int(np.ceil(np.log2(n))))


def graycode_patterns(width: int, height: int):
    """Return (patterns, inverses) uint8 images; columns bits first (MSB first), then rows."""
    gx = np.arange(width)
    gy = np.arange(height)
    pats = []
    for axis, n, g in (("x", width, gx), ("y", height, gy)):
        gray = g ^ (g >> 1)
        for b in range(_nbits(n) - 1, -1, -1):
            line = ((gray >> b) & 1).astype(np.uint8) * 255
            img = np.tile(line[None, :], (height, 1)) if axis == "x" else np.tile(line[:, None], (1, width))
            pats.append(img)
    return pats, [255 - p for p in pats]


@dataclass
class Decoded:
    """Per camera pixel: projector coordinate (px, py) and validity."""
    px: np.ndarray
    py: np.ndarray
    valid: np.ndarray


def decode_graycode(captures, inverses, proj_size, margin: int = 20) -> Decoded:
    """captures/inverses: camera images (gray or BGR) for each pattern/inverse in graycode order."""
    w, h = proj_size
    nx, ny = _nbits(w), _nbits(h)
    if len(captures) != nx + ny or len(inverses) != len(captures):
        raise ValueError(f"need {nx + ny} pattern/inverse pairs")
    gray = lambda im: im if im.ndim == 2 else cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    shape = gray(captures[0]).shape
    valid = np.ones(shape, bool)
    bits = []
    for c, i in zip(captures, inverses):
        d = gray(c).astype(np.int16) - gray(i).astype(np.int16)
        valid &= np.abs(d) > margin
        bits.append((d > 0).astype(np.int64))

    def to_bin(bs):
        g = np.zeros(shape, np.int64)
        for b in bs:
            g = (g << 1) | b
        v, s = g.copy(), g >> 1
        while s.any():
            v ^= s
            s >>= 1
        return v

    px, py = to_bin(bits[:nx]), to_bin(bits[nx:])
    valid &= (px < w) & (py < h)
    return Decoded(px, py, valid)


def proj_to_cam_mesh(dec: Decoded, proj_size, nodes=(17, 9), radius: int = 12, min_pixels: int = 6):
    """Camera position of each projector grid node (ny, nx, 2); NaN where not observed.

    Per node, fits an affine map (projector -> camera) to the decoded pixels within `radius`
    and evaluates it at the node, so border nodes are not biased by one-sided windows.
    """
    w, h = proj_size
    cy, cx = np.nonzero(dec.valid)
    ppx, ppy = dec.px[cy, cx].astype(np.float64), dec.py[cy, cx].astype(np.float64)
    cam = np.stack([cx, cy], 1).astype(np.float64)
    gx, gy = nodes
    out = np.full((gy, gx, 2), np.nan)
    for j, y in enumerate(np.linspace(0, h - 1, gy)):
        for i, x in enumerate(np.linspace(0, w - 1, gx)):
            sel = (np.abs(ppx - x) <= radius) & (np.abs(ppy - y) <= radius)
            if sel.sum() < min_pixels:
                continue
            A = np.stack([ppx[sel] - x, ppy[sel] - y, np.ones(sel.sum())], 1)
            if np.linalg.matrix_rank(A) < 3:
                continue
            coef, *_ = np.linalg.lstsq(A, cam[sel], rcond=None)
            out[j, i] = coef[2]
    return out


def cam_to_content_homography(cam_pts, content_pts):
    """Homography from >=4 camera points to content-space points (e.g. screen corners)."""
    H, _ = cv2.findHomography(np.asarray(cam_pts, np.float64), np.asarray(content_pts, np.float64), 0)
    if H is None:
        raise ValueError("degenerate correspondences")
    return H


def warp_mesh(cam_mesh, H):
    """Map camera-space node positions into content space: (ny, nx, 2), NaN preserved."""
    flat = cam_mesh.reshape(-1, 1, 2)
    ok = ~np.isnan(flat).any(axis=(1, 2))
    out = np.full(flat.shape, np.nan)
    if ok.any():
        out[ok] = cv2.perspectiveTransform(flat[ok], H)
    return out.reshape(cam_mesh.shape)


def coverage_mask(mesh, content_size) -> np.ndarray:
    """Rasterise the mesh quads (content pixels) into a boolean coverage mask."""
    w, h = content_size
    m = np.zeros((h, w), np.uint8)
    for j in range(mesh.shape[0] - 1):
        for i in range(mesh.shape[1] - 1):
            q = np.array([mesh[j, i], mesh[j, i + 1], mesh[j + 1, i + 1], mesh[j + 1, i]])
            if not np.isnan(q).any():
                cv2.fillConvexPoly(m, q.round().astype(np.int32), 1)
    return m.astype(bool)


def edge_blend_weights(masks, gamma: float = 2.2):
    """Per-projector blend alpha in content space (float32, linear-light weights, gamma-encoded).

    Weight = distance to the projector's own edge; normalised so overlaps sum to 1 (before gamma).
    Returns (alphas, linear_weights).
    """
    dist = [cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 3) for m in masks]
    total = np.sum(dist, axis=0)
    lin = [np.divide(d, total, out=np.zeros_like(d), where=total > 0).astype(np.float32) for d in dist]
    return [a ** (1.0 / gamma) for a in lin], lin
