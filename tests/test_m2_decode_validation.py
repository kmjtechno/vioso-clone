import numpy as np
import pytest

from vclone import calib

PW, PH = 64, 48


def _caps(h=20, w=30, n=None):
    n = n or len(calib.graycode_patterns(PW, PH)[0])
    return [np.full((h, w), 200, np.uint8) for _ in range(n)], [np.full((h, w), 10, np.uint8) for _ in range(n)]


@pytest.mark.parametrize("size", [(0, 48), (64, 0), (-5, 48), (64.5, 48), (64,), None, "ab", (True, 48)])
def test_decode_rejects_bad_proj_size(size):
    pos, neg = _caps()
    with pytest.raises(ValueError, match="proj_size"):
        calib.decode_graycode(pos, neg, size)


@pytest.mark.parametrize("margin", [-1, -0.5, float("nan"), float("inf"), "20", None, True])
def test_decode_rejects_bad_margin(margin):
    pos, neg = _caps()
    with pytest.raises(ValueError, match="margin"):
        calib.decode_graycode(pos, neg, (PW, PH), margin=margin)


def test_decode_rejects_mismatched_capture_shapes():
    pos, neg = _caps()
    pos[3] = np.zeros((10, 10), np.uint8)
    with pytest.raises(ValueError, match="shape"):
        calib.decode_graycode(pos, neg, (PW, PH))
    pos, neg = _caps()
    neg[0] = np.zeros((20, 31), np.uint8)
    with pytest.raises(ValueError, match="shape"):
        calib.decode_graycode(pos, neg, (PW, PH))


def test_decode_still_works_on_good_input():
    pos, neg = _caps()
    dec = calib.decode_graycode(pos, neg, (PW, PH))
    assert dec.valid.shape == (20, 30) and dec.valid.any()


def _dec():
    pos, neg = _caps()
    return calib.decode_graycode(pos, neg, (PW, PH))


@pytest.mark.parametrize("nodes", [(0, 5), (1, 1), (5, 0), (2.5, 3), (5,), None, (True, 4), (-3, 4)])
def test_mesh_rejects_bad_nodes(nodes):
    with pytest.raises(ValueError, match="nodes"):
        calib.proj_to_cam_mesh(_dec(), (PW, PH), nodes=nodes)


@pytest.mark.parametrize("kw,match", [
    ({"radius": 0}, "radius"), ({"radius": -1}, "radius"), ({"radius": float("nan")}, "radius"),
    ({"min_pixels": 2}, "min_pixels"), ({"min_pixels": 0}, "min_pixels"), ({"min_pixels": 3.5}, "min_pixels"),
])
def test_mesh_rejects_bad_radius_and_min_pixels(kw, match):
    with pytest.raises(ValueError, match=match):
        calib.proj_to_cam_mesh(_dec(), (PW, PH), **kw)


@pytest.mark.parametrize("size", [(0, 48), (64, -1), (6.5, 4), None])
def test_mesh_rejects_bad_proj_size(size):
    with pytest.raises(ValueError, match="proj_size"):
        calib.proj_to_cam_mesh(_dec(), size)


def test_mesh_minimum_valid_nodes_two_by_two():
    assert calib.proj_to_cam_mesh(_dec(), (PW, PH), nodes=(2, 2)).shape == (2, 2, 2)
