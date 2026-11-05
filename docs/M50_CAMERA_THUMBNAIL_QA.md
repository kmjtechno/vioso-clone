# M50 — One-time CP PLUS fisheye thumbnail (owner-local only)

The CP PLUS fisheye camera is not fully verified by a successful RTSP/ONVIF
login or a 2560 × 2560 frame-size report. A camera may be in a dewarped
2P/4R panorama instead of the original 1O fisheye mode.

M50 makes the M49 **Calibration > Connect ONVIF camera (no saved
credentials)...** action display **one bounded grayscale thumbnail** after
the two explicit camera-only consent gates and six actual frames. It lets
the P520 operator visually inspect whether the selected source appears to
be a circular raw/original fisheye view, while BOTH projectors are OFF.

## What the one-time preview does

- The frame probe reports the same aggregate source type, observed
  dimensions, frame count and exposure as before.
- **Only in the already-consented GUI ONVIF quick probe**, a fresh small
  thumbnail (maximum 320×240, grayscale uint8) is emitted through a
  Qt image signal after frame acquisition. The visible dialog is labeled
  **not calibrated**.
- No camera pixels are written to source control, profiles, calibration
  projects, reports, logs or an image file by this feature. The regular
  CLI, existing camera-profile file probe and default camera-frame-probe
  API still return only aggregate diagnostics.
- The separate CPU content preview and PNG export button do not store or
  export this camera thumbnail.
- No projectors are started or toggled. No automatic raw-mode changes or
  vendor camera commands occur.

## Acceptance steps

1. Launch the latest M50 portable Windows alpha GUI locally on P520.
2. Select Calibration → Connect ONVIF camera (no saved credentials).
3. Supply actual CP PLUS camera private IPv4/ONVIF port/read-only credentials
   **on that PC only**, choose the correct real profile token if needed.
4. Confirm checkbox and the second Yes dialog (both are required).
5. Verify receipt: 6 frames acquired, stable expected native camera
   resolution, reasonable exposure, projector operation NONE.
6. View one grayscale thumbnail. Confirm it is the original/raw fisheye
   circle, not a dewarped strip or split view. Seeing it is
   **manual plausibility**, NOT a lens calibration or measurement.
7. Keep projectors OFF until checkerboard intrinsic calibration and owner
   hardware mapping are ready. The owner will then explicitly turn ON both
   projectors for optically measured Gray-code alignment and seam/blend QA.

This does not prove camera firmware login or raw 1O if the P520 has not
actually been used. The project also lacks signed commercial installer and
independently verified vendor VIOSO 7 SPS interchange. Track remaining
gates in [Issue #67](https://github.com/kmjtechno/vioso-clone/issues/67).

Implementation is independent, testable with NumPy synthetic frames and
zero additional paid provider costs.
