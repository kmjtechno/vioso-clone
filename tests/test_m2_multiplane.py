import cv2
import numpy as np
import pytest

from vclone import calib

H1 = np.array([[1.2, 0.1, 30.0], [-0.05, 0.9, 12.0], [1e-4, 2e-4, 1.0]])
H2 = np.array([[0.7, -0.3, 400.0], [0.2, 1.1, -40.0], [-2e-4, 1e-4, 1.0]])


def _apply(H, pts):
    if len(pts) == 0:
        return np.empty((0, 2))
    return cv2.perspectiveTransform(np.asarray(pts, np.float64).reshape(-1, 1, 2), H).reshape(-1, 2)


def _scene(n1=60, n2=40, n_out=6, noise=0.0, seed=3):
    rng = np.random.default_rng(seed)
    c1 = np.column_stack([rng.uniform(0, 300, n1), rng.uniform(0, 400, n1)])
    c2 = np.column_stack([rng.uniform(340, 640, n2), rng.uniform(0, 400, n2)])
    p1 = _apply(H1, c1) + rng.normal(0, noise, (n1, 2))
    p2 = _apply(H2, c2) + rng.normal(0, noise, (n2, 2))
    co = np.column_stack([rng.uniform(0, 640, n_out), rng.uniform(0, 400, n_out)])
    po = np.column_stack([rng.uniform(0, 900, n_out), rng.uniform(0, 700, n_out)])
    cam = np.vstack([c1, c2, co])
    prj = np.vstack([p1, p2, po])
    return cam, prj, (n1, n2, n_out)


def test_two_planes_recovered_and_outliers_left_unassigned():
    cam, prj, (n1, n2, n_out) = _scene(noise=0.05)
    res = calib.fit_planes(cam, prj)
    assert len(res.planes) == 2
    assert [len(p.indices) for p in res.planes] == [n1, n2]  # largest support first
    assert set(res.planes[0].indices) == set(range(n1))
    assert set(res.planes[1].indices) == set(range(n1, n1 + n2))
    assert set(res.unassigned) == set(range(n1 + n2, n1 + n2 + n_out))
    for plane, truth, sl in ((res.planes[0], H1, slice(0, n1)), (res.planes[1], H2, slice(n1, n1 + n2))):
        err = np.linalg.norm(_apply(plane.h, cam[sl]) - _apply(truth, cam[sl]), axis=1)
        assert err.max() < 0.5 and plane.rms_px < 0.2


def test_partition_has_no_overlap_and_no_loss():
    cam, prj, _ = _scene(noise=0.05)
    res = calib.fit_planes(cam, prj)
    seen = [i for p in res.planes for i in p.indices] + list(res.unassigned)
    assert sorted(seen) == list(range(len(cam)))


def test_deterministic_for_same_input_and_seed():
    cam, prj, _ = _scene(noise=0.05)
    a, b = calib.fit_planes(cam, prj, seed=7), calib.fit_planes(cam, prj, seed=7)
    assert [p.indices for p in a.planes] == [p.indices for p in b.planes]
    assert all(np.array_equal(x.h, y.h) for x, y in zip(a.planes, b.planes))


def test_single_plane_gives_one_plane():
    cam, prj, (n1, _, _) = _scene(n2=0, n_out=0, noise=0.05)
    res = calib.fit_planes(cam, prj)
    assert len(res.planes) == 1 and len(res.planes[0].indices) == n1 and res.unassigned == []


def test_max_planes_is_respected_and_rest_unassigned():
    cam, prj, (n1, n2, n_out) = _scene(noise=0.05)
    res = calib.fit_planes(cam, prj, max_planes=1)
    assert len(res.planes) == 1
    assert len(res.unassigned) == n2 + n_out


def test_small_group_below_min_plane_points_is_not_forced_into_a_plane():
    cam, prj, (n1, _, _) = _scene(n2=8, n_out=0, noise=0.05)
    res = calib.fit_planes(cam, prj, min_plane_points=12)
    assert len(res.planes) == 1 and len(res.unassigned) == 8


def test_pure_noise_fails_closed():
    rng = np.random.default_rng(1)
    cam, prj = rng.uniform(0, 600, (60, 2)), rng.uniform(0, 600, (60, 2))
    with pytest.raises(ValueError, match="no plane"):
        calib.fit_planes(cam, prj)


@pytest.mark.parametrize("cam,prj,why", [
    (np.zeros((5, 2)), np.zeros((5, 2)), "too few"),
    (np.zeros((20, 2)), np.zeros((19, 2)), "same number"),
    (np.full((20, 2), np.nan), np.zeros((20, 2)), "non-finite"),
])
def test_bad_input_fails_closed(cam, prj, why):
    with pytest.raises(ValueError, match=why):
        calib.fit_planes(cam, prj)


def test_collinear_points_never_become_a_plane():
    t = np.linspace(0, 500, 40)
    cam = np.column_stack([t, 0.5 * t])
    prj = np.column_stack([2 * t, t])
    with pytest.raises(ValueError, match="no plane"):
        calib.fit_planes(cam, prj)
