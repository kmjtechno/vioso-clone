"""Software warp + edge-blend renderer (CPU, numpy/OpenCV).

Turns a calibration mesh (projector node -> content pixel) into the frame a projector must
show. GPU swap-chain output (DX/GL) needs a display device and is not implemented: it raises
UnsupportedOutput instead of pretending.
"""
import cv2
import numpy as np


_MAX_SIDE = 16384
# CPU interpolation builds multiple float64 arrays per output pixel.
# Cap at two 4K UHD frames' pixels rather than allowing 128M pixels (>several GB).
_MAX_PIXELS = 2 * 4096 * 2160


class UnsupportedOutput(NotImplementedError):
    pass


def _lerp_axis(a, axis, n):
    """Linearly resample axis of `a` from its length to n samples spanning the same end points."""
    m = a.shape[axis]
    t = np.linspace(0, m - 1, n)
    i0 = np.minimum(t.astype(int), m - 2)
    f = (t - i0).reshape([-1 if d == axis else 1 for d in range(a.ndim)])
    return np.take(a, i0, axis=axis) * (1 - f) + np.take(a, i0 + 1, axis=axis) * f


def render_projector(content, mesh, proj_size, alpha=None):
    """Warp `content` (h,w[,c]) into a projector frame of proj_size=(w,h).

    mesh: (ny,nx,2) content-space position of each projector grid node (NaN = unobserved),
    nodes evenly spaced over the projector. alpha: optional (ch,cw) float blend in content
    space. Pixels not covered by a fully observed quad are black.
    """
    if not isinstance(content, np.ndarray) or content.ndim not in (2, 3) or content.size == 0:
        raise ValueError("content must be a non-empty (h, w) or (h, w, c) array")
    if (content.dtype not in (np.uint8, np.uint16, np.int16, np.float32, np.float64)
            or (content.ndim == 3 and content.shape[2] not in (1, 2, 3, 4))):
        raise ValueError("content has unsupported channels or pixel dtype")
    mesh = np.asarray(mesh, np.float64)
    if mesh.ndim != 3 or mesh.shape[2] != 2 or mesh.shape[0] < 2 or mesh.shape[1] < 2:
        raise ValueError("mesh must be (ny>=2, nx>=2, 2)")
    ch, cw = content.shape[:2]
    if alpha is not None:
        alpha = np.asarray(alpha, np.float32)
        if alpha.shape != (ch, cw):
            raise ValueError("alpha must match content size")
        if not np.isfinite(alpha).all() or alpha.min() < 0 or alpha.max() > 1:
            raise ValueError("alpha must be finite and within [0, 1]")
    try:
        good = len(proj_size) == 2 and all(
            isinstance(v, (int, np.integer)) and not isinstance(v, bool) and 0 < v <= _MAX_SIDE
            for v in proj_size)
    except TypeError:
        good = False
    if not good:
        raise ValueError(f"proj_size must be two integers in 1..{_MAX_SIDE}: {proj_size!r}")
    w, h = int(proj_size[0]), int(proj_size[1])
    if w * h > _MAX_PIXELS:
        raise ValueError(f"proj_size too large (max {_MAX_PIXELS} pixels): {proj_size!r}")
    ok = np.isfinite(mesh).all(axis=2)  # NaN and +-inf nodes are both unobserved
    # sample the node grid at each projector pixel (nodes sit at linspace(0, w-1) / linspace(0, h-1));
    # validity is interpolated alongside so NaN nodes do not bleed into neighbours
    ny, nx = ok.shape
    wgt = ok.astype(np.float64)
    num = np.concatenate([np.where(ok[..., None], mesh, 0.0), wgt[..., None]], axis=2)  # (ny,nx,3)
    num[..., :2] *= wgt[..., None]
    num = _lerp_axis(num, 1, w)
    num = _lerp_axis(num, 0, h)
    den = num[..., 2]
    num = num[..., :2]
    full = den > 0.999
    maps = np.divide(num, den[..., None], out=np.zeros_like(num), where=den[..., None] > 1e-6).astype(np.float32)
    out = cv2.remap(content, maps[..., 0], maps[..., 1], cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    if alpha is not None:
        a = cv2.remap(alpha, maps[..., 0], maps[..., 1], cv2.INTER_LINEAR,
                      borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        out = (out.astype(np.float32) * (a[..., None] if out.ndim == 3 else a)).round().astype(content.dtype)
    out[~full] = 0
    return out


def present(backend, frame):
    """Send a frame to a display. Only a real GPU/window backend can do this; none is built in."""
    raise UnsupportedOutput(f"output backend {backend!r} is not implemented (needs a display device)")
