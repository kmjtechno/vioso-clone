# M56 — Visual camera preflight and guided software calibration checklist

This is a functional PySide6 + NumPy feature update for the independent
KMJ VIOSO Clone alpha. The product already contains Gray-code capture,
homography, CPU warp mesh, multi-projector blend/export, synthetic optical
checks and JSON project persistence. M56 makes two previously missing
steps useful before any projector power-on.

## 1. One non-persistent fisheye preview

Connect ONVIF Camera still requires the checkbox and separate Yes
confirmation before it touches the camera. After successful six-frame
acquisition, explicit return_preview=True returns the unchanged
credential-safe diagnostic report plus one bounded grayscale copy
(up to 320×240) to the GUI. A separate non-exportable Qt dialog displays
that frame to inspect raw 1O circular fisheye versus vendor-dewarped mode.

There is no image file, webcam recording, calibration acceptance, source
JSON write or projector output. The existing non-GUI camera_frame_probe()
API remains report-only by default. The standalone CPU calibrated-content
preview and its PNG export feature never receive camera pixels.

This is an observational visual check, not lens intrinsic calibration.

## 2. Eight-stage offline workflow checklist

The new Workflow Checklist action in the top toolbar and menu shows
a read-only software readiness breakdown from current project metadata:

1. Camera-only preflight
2. Fisheye lens intrinsics
3. Two-projector Windows display mapping
4. Gray-code capture setup
5. Camera/content corner correspondence
6. Warp mesh calibration
7. Multi-projector seam and blend
8. Clone-format project export

A configured scan folder, existing mesh or two display objects only yields
CONFIGURED_NOT_VERIFIED, SOFTWARE_RESULT_PRESENT_NOT_VERIFIED, etc.
No synthetic project field or copied saved JSON can ever produce actual
physical PASS. The status viewer never reads the camera, enumerates devices,
opens the filesystem or starts a projector.

Existing captured-image, calibrated-preview and export commands remain
unchanged. All previously documented user confirmations still apply.

## Independent release gates

- Offline Python tests: default source API, explicit consent, bounded
  small frame, no files and no pixels in receipts.
- Offscreen Qt tests: one QImage only for opt-in, no content preview/PNG
  contamination, unchanged menu and current project status, checklist
  button wired to a real action.
- Full exact-head Linux/Windows CI and Windows frozen GUI self-test.
- Real CP PLUS frames and raw-1O review, physical checkerboard intrinsics,
  both powered projectors, measured seam/black-level and native VIOSO 7
  file compatibility all remain NOT VERIFIED until separate evidence.

An unsigned software alpha is not a signed commercial release.
