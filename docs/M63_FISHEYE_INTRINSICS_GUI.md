# M63 — Measured fisheye intrinsics and camera ROI from guided wizard

Functional offline Qt workflow to generate a real OpenCV fisheye lens model from checkerboard photos.
This does not guess a CP PLUS factory calibration or load protected vendor code.

## Use

1. Capture a real Gray-code session from the camera, projectors only when owner authorized.
2. Gather 12–48 distinct sharp checkerboard photos from the same physical camera at the same exact capture resolution.
3. In the M62 Guided Calibration Wizard, open Scan Quality & Fisheye then Measure fisheye lens from checkerboard photos.
4. Choose photo folder, inner-corner grid (default 9x6), physical checkerboard square size (default 25 mm), and max RMS (default 1.5 px).
5. Choose a NEW JSON basename inside existing capture folder. Check explicit consent, then run the background M32 solver.
6. OpenCV must detect all boards, have adequate spatial coverage, diverse tilted views, plausible camera matrix and bounded RMS.
7. Only after valid measurements and matching capture resolution is a NEW JSON profile saved without replacing owner data.
8. Wizard asks for a separate Yes before attaching the new profile because lens coordinate-frame change invalidates previous corners and mesh.
9. Revisit Surface Geometry to select four corners on the newly rectified camera image, and run the quality-gated warp solve.

## Camera region-of-interest mask

Scan Quality & Fisheye also supports an existing binary grayscale camera ROI PNG placed in the same capture folder.
Black (0) INCLUDES a camera pixel, white (255) EXCLUDES it. Anti-aliased gray pixels are refused.
Width/height must exactly match captured camera frames. Setting a new ROI invalidates stale corners, mesh and export.
This is a camera-side mask, different from the M62 projector-side grayscale projection mask.

## Safety and limits

Opening the lens dialog and choosing checkerboard photos never opens camera, projector or network hardware.
The M32 worker runs in a Qt background thread and sanitizes all exceptions before UI display.
Photos and scan captures are read-only. Only a separately consented NEW profile JSON file is written.
Profile output uses an exclusive-create operation and rejects symlinks/overwrites, non-finite or implausible lens measurements.
Neither software RMS nor computed intrinsics certifies raw fisheye sensor mode, actual field-of-view, physical multi-projector alignment or native VIOSO 7 parity.
Hardware optical acceptance, native SPS/3D/dome calibration, GPU-synchronized NDI playback and signed Windows release remain independently blocked.