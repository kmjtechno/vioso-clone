import numpy as np
import pytest

from vclone import configs, intrinsics

SIZE = (1280, 960)
TRUTH = configs.CameraIntrinsics("t", *SIZE, 1500.0, 1510.0, 640.0, 480.0, -0.12, 0.08, 0.0, 0.0005, -0.0004)
BOARD = np.stack([*(m.ravel() for m in np.meshgrid(np.arange(9) * 30.0, np.arange(6) * 30.0)),
                  np.zeros(54)], 1)


def _views(n, tilt, centre=(-120, -75), spread=40.0, seed=1, z=600.0):
    rng = np.random.default_rng(seed)
    objs, imgs = [], []
    for _ in range(n):
        r = rng.uniform(-tilt, tilt, 3)
        t = np.array([centre[0], centre[1], z]) + rng.uniform(-spread, spread, 3)
        objs.append(BOARD)
        imgs.append(intrinsics.project(TRUTH, BOARD, r, t))
    return objs, imgs


def test_good_capture_passes_all_gates():
    objs, imgs = _views(16, tilt=0.6, spread=160.0)
    est, rms, reasons = intrinsics.calibrate_with_gates(objs, imgs, SIZE)
    assert reasons == [] and rms < 0.1
    assert abs(est.fx - TRUTH.fx) / TRUTH.fx < 0.02


def test_too_few_views_is_rejected():
    objs, imgs = _views(5, tilt=0.6, spread=160.0)
    _, _, reasons = intrinsics.calibrate_with_gates(objs, imgs, SIZE)
    assert any("too few views" in r for r in reasons)


def test_flat_board_without_tilt_is_rejected():
    objs, imgs = _views(14, tilt=0.02, spread=160.0)
    _, _, reasons = intrinsics.calibrate_with_gates(objs, imgs, SIZE)
    assert any("tilt" in r for r in reasons)


def test_clustered_board_without_image_coverage_is_rejected():
    objs, imgs = _views(14, tilt=0.6, spread=5.0, centre=(-60, -40), z=1500.0)  # small, central
    _, _, reasons = intrinsics.calibrate_with_gates(objs, imgs, SIZE)
    assert any("coverage" in r for r in reasons)


def test_noisy_corners_fail_the_rms_gate():
    objs, imgs = _views(16, tilt=0.6, spread=160.0)
    rng = np.random.default_rng(7)
    noisy = [i + rng.normal(0, 3.0, i.shape) for i in imgs]
    _, rms, reasons = intrinsics.calibrate_with_gates(objs, noisy, SIZE)
    assert rms > 1.0 and any("rms" in r for r in reasons)


def test_checked_raises_with_every_reason_and_never_returns_a_profile():
    objs, imgs = _views(5, tilt=0.02, spread=5.0, centre=(-60, -40), z=1500.0)
    with pytest.raises(intrinsics.IntrinsicsRejected) as e:
        intrinsics.calibrate_checked(objs, imgs, SIZE)
    assert len(e.value.reasons) >= 3


def test_checked_returns_profile_when_gates_pass():
    objs, imgs = _views(16, tilt=0.6, spread=160.0)
    est, rms = intrinsics.calibrate_checked(objs, imgs, SIZE)
    assert est.width == 1280 and rms < 0.1

def test_coverage_excludes_fully_offscreen_points():
    # P0 regression: clamping y=-50 and y=1010 to frame edges once
    # produced 8/12 = 66.7% coverage although all pixels were off-screen.
    points = np.array([(x, y) for x in (160, 480, 800, 1120)
                       for y in (-50, 1010)], dtype=np.float64)
    assert intrinsics.coverage_fraction([points], SIZE) == 0.0
    reasons = intrinsics.quality_reasons(
        0.0, [np.array([[0.5], [0.0], [0.0]])] * 16,
        [points] * 16, SIZE)
    assert any("coverage" in r for r in reasons)


def test_coverage_excludes_nonfinite_and_outside_points_without_clamping():
    points = np.array([(100, 100), (np.nan, 100), (100, np.inf),
                       (-1, 900), (1280, 100), (100, 960)], dtype=np.float64)
    # The sole valid point counts toward exactly one of twelve cells.
    assert intrinsics.coverage_fraction([points], SIZE) == pytest.approx(1 / 12)


@pytest.mark.parametrize("dimensions", [
    (0, 960), (1280, 0), (-1, 960), (1280, float("nan")),
    (1280, float("inf")), (1280,),
])
def test_coverage_rejects_invalid_image_dimensions(dimensions):
    with pytest.raises(ValueError, match="positive finite image dimensions"):
        intrinsics.coverage_fraction([[(100, 100)]], dimensions)
