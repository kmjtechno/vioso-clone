"""Calibration engine: Gray-code scan, camera<->projector map, warp mesh, edge blend.

Clean-room design; operates on arrays so it is testable without hardware.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


def _pos_int(v) -> bool:
    return isinstance(v, (int, np.integer)) and not isinstance(v, bool) and v > 0


def _check_pair(value, label, minimum=1):
    try:
        ok = len(value) == 2 and all(_pos_int(v) and v >= minimum for v in value)
    except TypeError:
        ok = False
    if not ok:
        raise ValueError(f"{label} must be two integers >= {minimum}: {value!r}")
    return int(value[0]), int(value[1])


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
    w, h = _check_pair(proj_size, "proj_size")
    if isinstance(margin, bool) or not isinstance(margin, (int, float)) or not np.isfinite(margin) or margin < 0:
        raise ValueError(f"margin must be a finite number >= 0: {margin!r}")
    nx, ny = _nbits(w), _nbits(h)
    if len(captures) != nx + ny or len(inverses) != len(captures):
        raise ValueError(f"need {nx + ny} pattern/inverse pairs")
    gray = lambda im: im if im.ndim == 2 else cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    shape = gray(captures[0]).shape
    if any(gray(im).shape != shape for im in list(captures) + list(inverses)):
        raise ValueError("all captures and inverses must have the same shape")
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
    w, h = _check_pair(proj_size, "proj_size")
    gx, gy = _check_pair(nodes, "nodes", minimum=2)
    if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not np.isfinite(radius) or radius <= 0:
        raise ValueError(f"radius must be a finite number > 0: {radius!r}")
    if not _pos_int(min_pixels) or min_pixels < 3:
        raise ValueError(f"min_pixels must be an integer >= 3 (affine fit): {min_pixels!r}")
    cy, cx = np.nonzero(dec.valid)
    ppx, ppy = dec.px[cy, cx].astype(np.float64), dec.py[cy, cx].astype(np.float64)
    cam = np.stack([cx, cy], 1).astype(np.float64)
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


def _check_spread(pts, label, min_area_fraction):
    """Reject collinear or clustered point sets: convex-hull area vs bounding-box area."""
    span = pts.max(0) - pts.min(0)
    bbox = float(span[0] * span[1])
    hull = cv2.contourArea(cv2.convexHull(pts.astype(np.float32))) if len(pts) >= 3 else 0.0
    if bbox <= 0 or hull < min_area_fraction * bbox:
        raise ValueError(f"degenerate geometry: {label} points collinear or clustered")


def cam_to_content_homography(cam_pts, content_pts, max_rms=1.0, min_area_fraction=0.02):
    """Homography from >=4 camera points to content-space points (e.g. screen corners).

    Fails closed (ValueError) instead of returning a guessed fit: too few or mismatched
    points, non-finite values, collinear/clustered geometry on either side, a fit that sends
    an input point through infinity, or reprojection RMS above `max_rms` (content units).
    """
    cam = np.asarray(cam_pts, np.float64).reshape(-1, 2)
    con = np.asarray(content_pts, np.float64).reshape(-1, 2)
    if len(cam) != len(con):
        raise ValueError("camera and content need the same number of points")
    if len(cam) < 4:
        raise ValueError("need at least 4 correspondences")
    if not (np.isfinite(cam).all() and np.isfinite(con).all()):
        raise ValueError("non-finite correspondence")
    _check_spread(cam, "camera", min_area_fraction)
    _check_spread(con, "content", min_area_fraction)
    H, _ = cv2.findHomography(cam, con, 0)
    if H is None or not np.isfinite(H).all() or abs(H[2, 2]) < 1e-12:
        raise ValueError("degenerate geometry: no valid homography")
    H = H / H[2, 2]
    w = cam @ H[2, :2] + H[2, 2]
    w = w * np.sign(w[np.argmax(np.abs(w))])  # all points must sit on one side of the horizon
    if not (w > 1e-9 * np.abs(w).max()).all():
        raise ValueError("degenerate geometry: a point maps through infinity")
    proj = cv2.perspectiveTransform(cam.reshape(-1, 1, 2), H).reshape(-1, 2)
    rms = float(np.sqrt(np.mean(np.sum((proj - con) ** 2, axis=1))))
    if not rms <= max_rms:
        raise ValueError(f"reprojection RMS {rms:.3f} exceeds gate {max_rms}")
    return H


@dataclass
class PlaneFit:
    h: np.ndarray        # camera -> projector homography, h[2, 2] == 1
    rms_px: float        # reprojection RMS over `indices`
    indices: list        # indices into the input correspondences


@dataclass
class MultiPlane:
    planes: list         # PlaneFit, largest support first
    unassigned: list     # indices that fit no accepted plane (never forced into one)


def _side(H, cam):
    """+1/-1: which side of the horizon line the points sit on (they must all agree)."""
    w = cam @ H[2, :2] + H[2, 2]
    return 1.0 if w[np.argmax(np.abs(w))] > 0 else -1.0


def _inliers(H, side, cam, prj, pool, tol):
    c = cam[pool]
    w = (c @ H[2, :2] + H[2, 2]) * side
    ok = w > 1e-9
    err = np.full(len(pool), np.inf)
    if ok.any():
        q = cv2.perspectiveTransform(c[ok].reshape(-1, 1, 2), H).reshape(-1, 2)
        err[ok] = np.linalg.norm(q - prj[pool][ok], axis=1)
    return pool[err <= tol]


def fit_planes(cam_pts, proj_pts, *, min_plane_points=12, inlier_tol_px=1.0, max_planes=4,
               iterations=400, seed=12345, max_rms=1.0, min_area_fraction=0.02):
    """Split camera->projector correspondences that lie on several planar surfaces into one
    homography per plane (sequential RANSAC). Deterministic for a given seed.

    Every accepted plane passes the same gates as cam_to_content_homography; points that fit
    no accepted plane are returned as `unassigned`, never forced into a plane. Raises
    ValueError on too few/mismatched/non-finite input or when no plane has enough support.
    Port of the algorithm in the user's own KMJ CalibrationNew multiplane code.
    """
    cam = np.asarray(cam_pts, np.float64).reshape(-1, 2)
    prj = np.asarray(proj_pts, np.float64).reshape(-1, 2)
    if len(cam) != len(prj):
        raise ValueError("camera and projector need the same number of points")
    need = max(int(min_plane_points), 4)
    if len(cam) < need:
        raise ValueError("too few correspondences for a plane")
    if not (np.isfinite(cam).all() and np.isfinite(prj).all()):
        raise ValueError("non-finite correspondence")

    rng = np.random.default_rng(seed)
    pool = np.arange(len(cam))
    planes = []
    while len(planes) < max_planes and len(pool) >= need:
        best = np.empty(0, int)
        for _ in range(iterations):
            pick = rng.choice(pool, 4, replace=False)
            try:  # minimal samples fit exactly, so only the geometry gates apply here
                H = cam_to_content_homography(cam[pick], prj[pick], max_rms=1e9,
                                              min_area_fraction=min_area_fraction)
            except ValueError:
                continue
            inl = _inliers(H, _side(H, cam[pick]), cam, prj, pool, inlier_tol_px)
            if len(inl) > len(best):
                best = inl
        if len(best) < need:
            break
        try:  # refit on the consensus set with the full gates
            H = cam_to_content_homography(cam[best], prj[best], max_rms=max_rms,
                                          min_area_fraction=min_area_fraction)
        except ValueError:
            break
        inl = _inliers(H, _side(H, cam[best]), cam, prj, pool, inlier_tol_px)
        if len(inl) < need:
            break
        proj = cv2.perspectiveTransform(cam[inl].reshape(-1, 1, 2), H).reshape(-1, 2)
        rms = float(np.sqrt(np.mean(np.sum((proj - prj[inl]) ** 2, axis=1))))
        # Reclassification can add points not present in the gated refit set.
        # Never publish an expanded consensus whose actual RMS violates the gate.
        if not np.isfinite(rms) or rms > max_rms:
            break
        planes.append(PlaneFit(H, rms, sorted(int(i) for i in inl)))
        pool = np.setdiff1d(pool, inl)
    if not planes:
        raise ValueError("no plane with enough consistent support")
    planes.sort(key=lambda p: -len(p.indices))
    return MultiPlane(planes, [int(i) for i in pool])


def _check_mesh(mesh, name="mesh", min_nodes=1):
    m = np.asarray(mesh, np.float64) if mesh is not None else None
    if m is None or m.ndim != 3 or m.shape[2] != 2 or m.shape[0] < min_nodes or m.shape[1] < min_nodes:
        raise ValueError(f"{name} must have shape (ny, nx, 2) with at least {min_nodes} node(s) per axis")
    return m


def warp_mesh(cam_mesh, H):
    """Map camera-space node positions into content space: (ny, nx, 2), NaN preserved.

    Fails closed on a non-3x3, non-finite or singular homography. Nodes that map through the
    horizon (w ~ 0) or to a non-finite result become NaN instead of garbage.
    """
    mesh = _check_mesh(cam_mesh)
    try:
        Hm = np.asarray(H, np.float64)
    except (TypeError, ValueError):
        raise ValueError("homography must be a numeric 3x3 matrix") from None
    if Hm.shape != (3, 3) or not np.isfinite(Hm).all():
        raise ValueError("homography must be a finite 3x3 matrix")
    if abs(np.linalg.det(Hm)) <= 1e-12 * max(1.0, np.abs(Hm).max()) ** 3:
        raise ValueError("homography is singular")
    flat = mesh.reshape(-1, 2)
    out = np.full(flat.shape, np.nan)
    ok = np.isfinite(flat).all(axis=1)
    hom = np.c_[flat[ok], np.ones(ok.sum())] @ Hm.T
    w = hom[:, 2]
    good = np.abs(w) > 1e-9 * max(1.0, np.abs(hom).max())
    res = np.full((len(w), 2), np.nan)
    res[good] = hom[good, :2] / w[good, None]
    res[~np.isfinite(res).all(axis=1)] = np.nan
    out[ok] = res
    return out.reshape(mesh.shape)


_MAX_COORD = 1e8  # cv2 rasterises in int32; quads beyond this are skipped, not wrapped


def coverage_mask(mesh, content_size) -> np.ndarray:
    """Rasterise the mesh quads (content pixels) into a boolean coverage mask.

    Quads with a NaN, infinite or absurdly large (> 1e8) corner are skipped, never wrapped.
    """
    mesh = _check_mesh(mesh, min_nodes=2)
    try:
        ok = len(content_size) == 2 and all(
            isinstance(v, (int, np.integer)) and not isinstance(v, bool) and v > 0 for v in content_size)
    except TypeError:
        ok = False
    if not ok:
        raise ValueError(f"content_size must be two positive integers: {content_size!r}")
    w, h = int(content_size[0]), int(content_size[1])
    m = np.zeros((h, w), np.uint8)
    for j in range(mesh.shape[0] - 1):
        for i in range(mesh.shape[1] - 1):
            q = np.array([mesh[j, i], mesh[j, i + 1], mesh[j + 1, i + 1], mesh[j + 1, i]])
            if np.isfinite(q).all() and np.abs(q).max() <= _MAX_COORD:
                cv2.fillConvexPoly(m, q.round().astype(np.int32), 1)
    return m.astype(bool)


def edge_blend_weights(masks, gamma: float = 2.2):
    """Per-projector blend alpha in content space (float32, linear-light weights, gamma-encoded).

    Weight = distance to the projector's own edge; normalised so overlaps sum to 1 (before gamma).
    Returns (alphas, linear_weights).
    """
    if isinstance(gamma, bool) or not isinstance(gamma, (int, float)) or not np.isfinite(gamma) or gamma <= 0:
        raise ValueError(f"gamma must be a finite positive number: {gamma!r}")
    masks = [np.asarray(m) for m in masks]
    if not masks:
        raise ValueError("need at least one mask")
    if any(m.ndim != 2 for m in masks):
        raise ValueError("every mask must be 2-D")
    if any(m.shape != masks[0].shape for m in masks):
        raise ValueError("all masks must have the same shape")
    dist = [cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 3) for m in masks]
    total = np.sum(dist, axis=0)
    lin = [np.divide(d, total, out=np.zeros_like(d), where=total > 0).astype(np.float32) for d in dist]
    return [a ** (1.0 / gamma) for a in lin], lin
