import numpy as np
import pytest

from vclone import calib

H_ID = np.eye(3)


def _grid(ny=3, nx=4, step=10.0):
    return np.array([[[i * step, j * step] for i in range(nx)] for j in range(ny)])


def test_identity_warp_preserves_mesh_and_nan():
    m = _grid()
    m[1, 1] = np.nan
    out = calib.warp_mesh(m, H_ID)
    assert np.isnan(out[1, 1]).all()
    ok = ~np.isnan(m)
    assert np.allclose(out[ok], m[ok])


@pytest.mark.parametrize("H", [
    np.zeros((3, 3)), np.eye(2), np.ones(9), np.full((3, 3), np.nan),
    np.array([[1, 0, 0], [0, 1, 0], [0, 0, np.inf]]), np.array([[1, 2, 3], [2, 4, 6], [1, 2, 3.0]]),
    "H", None,
])
def test_warp_mesh_rejects_bad_homography(H):
    with pytest.raises(ValueError, match="homography"):
        calib.warp_mesh(_grid(), H)


@pytest.mark.parametrize("mesh", [np.zeros((3, 4)), np.zeros((3, 4, 3)), np.zeros(5), None])
def test_warp_mesh_rejects_bad_mesh_shape(mesh):
    with pytest.raises(ValueError, match="mesh"):
        calib.warp_mesh(mesh, H_ID)


def test_warp_mesh_marks_points_mapped_through_infinity_as_nan():
    H = np.array([[1.0, 0, 0], [0, 1, 0], [0.1, 0, 1]])  # w = 0 at x = -10
    m = np.array([[[-10.0, 5.0], [10.0, 5.0]]])
    out = calib.warp_mesh(m, H)
    assert np.isnan(out[0, 0]).all() and np.isfinite(out[0, 1]).all()


@pytest.mark.parametrize("size", [(0, 10), (10, 0), (-1, 5), (5.5, 5), (10,), "ab", None, (True, 5)])
def test_coverage_mask_rejects_bad_content_size(size):
    with pytest.raises(ValueError, match="content_size"):
        calib.coverage_mask(_grid(), size)


@pytest.mark.parametrize("mesh", [np.zeros((3, 4)), np.zeros((3, 4, 3)), np.zeros((1, 4, 2)), None])
def test_coverage_mask_rejects_bad_mesh(mesh):
    with pytest.raises(ValueError, match="mesh"):
        calib.coverage_mask(mesh, (50, 50))


def test_coverage_mask_ignores_quads_with_infinite_or_huge_coordinates():
    m = _grid(2, 2, 20.0)
    m[1, 1] = (np.inf, 5.0)
    assert not calib.coverage_mask(m, (50, 50)).any()
    m2 = _grid(2, 2, 20.0)
    m2[1, 1] = (1e15, 1e15)
    assert not calib.coverage_mask(m2, (50, 50)).any()


def test_coverage_mask_fills_valid_quad_and_clips_to_raster():
    m = np.array([[[10.0, 10.0], [30.0, 10.0]], [[10.0, 30.0], [30.0, 30.0]]])
    mask = calib.coverage_mask(m, (50, 50))
    assert mask[20, 20] and not mask[40, 40] and mask.shape == (50, 50)
    far = m + 1000.0
    assert not calib.coverage_mask(far, (50, 50)).any()
