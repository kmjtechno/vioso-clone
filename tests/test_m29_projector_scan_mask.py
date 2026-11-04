"""M29 opt-in projector-space grayscale mask for Gray-code capture.

No physical camera or projector is used by these tests.
"""
import hashlib
import json

import cv2
import numpy as np
import pytest

from vclone import capture
from vclone.__main__ import main
from vclone.projector_mask import ProjectorMaskError, read_projector_mask


@pytest.fixture
def maskfile(tmp_path):
    path = tmp_path / "mask.png"
    mask = np.full((6, 8), 255, dtype=np.uint8)
    mask[:, :2] = 0
    mask[:, 2] = 128  # grayscale feathering, not binary
    assert cv2.imwrite(str(path), mask)
    return path, mask


def test_mask_loader_preserves_owner_png_bytes_and_gray_levels(maskfile):
    path, original = maskfile
    before = path.read_bytes()
    actual = read_projector_mask(path, (8, 6))
    np.testing.assert_array_equal(actual, original)
    assert actual.dtype == np.uint8
    assert path.read_bytes() == before


def test_masked_pattern_sequence_propagates_to_camera_and_manifest(maskfile, tmp_path):
    path, mask = maskfile
    original_bytes = path.read_bytes()
    current = [None]
    displayed = []

    def show(pattern):
        displayed.append(pattern.copy())
        current[0] = pattern.copy()

    def grab():
        return current[0].copy()

    outdir = tmp_path / "new"
    receipt = capture.capture_sequence(8, 6, outdir, show, grab,
                                       projector_mask=read_projector_mask(path, (8, 6)))
    patterns = list(capture.iter_patterns(8, 6))
    assert len(displayed) == len(patterns) == len(receipt.image_files)
    for (name, raw), displayed_frame in zip(patterns, displayed):
        np.testing.assert_array_equal(displayed_frame, cv2.bitwise_and(raw, mask))
        saved = cv2.imread(str(outdir / name), cv2.IMREAD_UNCHANGED)
        np.testing.assert_array_equal(saved, displayed_frame)
    metadata = json.loads((outdir / "capture_manifest.json").read_text())
    assert metadata["projector_mask_applied"] is True
    assert metadata["projector_mask_pixel_sha256"] == hashlib.sha256(mask.tobytes()).hexdigest()
    assert metadata["hardware_acceptance"] == "NOT_VERIFIED"
    assert path.read_bytes() == original_bytes


def test_unmasked_capture_sequence_retains_original_manifest_shape(tmp_path):
    current = [None]
    def show(frame):
        current[0] = frame
    def grab():
        return current[0]
    out = tmp_path / "plain"
    capture.capture_sequence(8, 6, out, show, grab)
    metadata = json.loads((out / "capture_manifest.json").read_text())
    assert "projector_mask_applied" not in metadata
    assert "projector_mask_pixel_sha256" not in metadata


@pytest.mark.parametrize("invalid", [
    np.zeros((6, 8), np.uint8),
    np.zeros((5, 8), np.uint8),
    np.zeros((6, 8, 3), np.uint8),
    np.full((6, 8), 255, np.float32),
])
def test_invalid_mask_blocks_before_creating_capture_directory(tmp_path, invalid):
    out = tmp_path / "bad-capture"
    with pytest.raises(capture.CaptureError, match="projector mask"):
        capture.capture_sequence(8, 6, out, lambda _: None, lambda: None,
                                 projector_mask=invalid)
    assert not out.exists()


def test_wrong_resolution_and_color_file_fail_closed(maskfile):
    path, _ = maskfile
    with pytest.raises(ProjectorMaskError, match="dimensions"):
        read_projector_mask(path, (6, 8))
    assert cv2.imwrite(str(path), np.zeros((6, 8, 3), dtype=np.uint8))
    with pytest.raises(ProjectorMaskError, match="grayscale"):
        read_projector_mask(path, (8, 6))


def test_projector_mask_symlink_rejected(maskfile, tmp_path):
    path, _ = maskfile
    linked = tmp_path / "mask-link.png"
    try:
        linked.symlink_to(path)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ProjectorMaskError, match="non-symlink"):
        read_projector_mask(linked, (8, 6))


def test_preflight_bad_mask_never_opens_camera_or_display(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(capture.cv2, "VideoCapture",
                        lambda *_args: opened.append(True))
    mask = tmp_path / "invalid.png"
    mask.write_bytes(b"not png")
    output = tmp_path / "not-created"
    with pytest.raises(ProjectorMaskError):
        capture.capture_opencv(8, 6, output, camera_index=0,
                               projector_x=100, projector_y=0,
                               confirmed=True, projector_mask_path=mask)
    assert opened == []
    assert not output.exists()


def test_cli_does_not_open_camera_without_display_confirmation(maskfile, tmp_path, capsys):
    path, _ = maskfile
    out = tmp_path / "never-start"
    result = main(["capture-graycode", "--width", "8", "--height", "6",
                   "--camera", "0", "--projector-x", "100",
                   "--projector-y", "0", "--out", str(out),
                   "--projector-mask", str(path)])
    assert result == 2
    assert "confirmation" in capsys.readouterr().err.lower()
    assert not out.exists()
