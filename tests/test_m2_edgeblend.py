import numpy as np
import pytest

from vclone import calib


def _m(h, w, x0, x1):
    m = np.zeros((h, w), bool)
    m[:, x0:x1] = True
    return m


def test_three_way_overlap_sums_to_one_everywhere_covered():
    ms = [_m(20, 120, 0, 60), _m(20, 120, 40, 90), _m(20, 120, 70, 120)]
    _, lin = calib.edge_blend_weights(ms)
    cov = ms[0] | ms[1] | ms[2]
    assert np.allclose(sum(lin)[cov], 1.0, atol=1e-5)
    assert all(l.dtype == np.float32 and (l >= 0).all() and (l <= 1).all() for l in lin)


def test_single_mask_gets_full_weight_inside_and_zero_outside():
    m = _m(10, 40, 5, 30)
    _, lin = calib.edge_blend_weights([m])
    assert np.allclose(lin[0][m], 1.0) and (lin[0][~m] == 0).all()


def test_alphas_stay_in_unit_range_and_zero_where_uncovered():
    ms = [_m(20, 100, 0, 60), _m(20, 100, 40, 100)]
    alphas, _ = calib.edge_blend_weights(ms)
    for a, m in zip(alphas, ms):
        assert (a >= 0).all() and (a <= 1.0 + 1e-6).all() and (a[~m] == 0).all()


@pytest.mark.parametrize("gamma", [0, -1, -2.2, float("nan"), float("inf"), "2.2", None, True])
def test_bad_gamma_fails_closed(gamma):
    with pytest.raises(ValueError, match="gamma"):
        calib.edge_blend_weights([_m(10, 10, 0, 10)], gamma=gamma)


def test_empty_mask_list_fails_closed():
    with pytest.raises(ValueError, match="mask"):
        calib.edge_blend_weights([])


def test_mismatched_mask_shapes_fail_closed():
    with pytest.raises(ValueError, match="shape"):
        calib.edge_blend_weights([_m(10, 10, 0, 10), _m(10, 12, 0, 12)])


@pytest.mark.parametrize("bad", [np.zeros(10, bool), np.zeros((2, 3, 4), bool)])
def test_non_2d_mask_fails_closed(bad):
    with pytest.raises(ValueError, match="2-D"):
        calib.edge_blend_weights([bad])


def test_gamma_one_produces_linear_alphas():
    masks = [_m(12, 50, 0, 32), _m(12, 50, 20, 50)]
    alphas, linear = calib.edge_blend_weights(masks, gamma=1.0)
    assert all(np.isfinite(a).all() for a in alphas)
    assert all(np.allclose(a, w) for a, w in zip(alphas, linear))
