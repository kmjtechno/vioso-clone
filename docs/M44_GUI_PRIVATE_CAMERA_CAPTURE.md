# M44 — Private CP PLUS / RTSP source in the Gray-code GUI capture

M33 already provided camera-source profiles for USB, RTSP/RTSPS, ONVIF-resolved
RTSP, MJPEG, video replay and separately registered SDK cameras. Its
`capture_opencv(... camera_profile_path=...)` API and CLI could select a
profile, but the GUI's M21 `Capture Gray-code from camera...` dialog still
hard-coded a USB camera index only. That was a concrete GUI blocker for
capturing using the owner's connected CP PLUS fisheye network camera.

M44 connects the *existing* validated camera-source pipeline to the GUI.
It makes **no promise** that a specific camera's RTSP settings, codec, native
fisheye frame, lens model or OS driver has been verified.

## User operation (owner P520)

1. With BOTH projectors still **OFF**, use Calibration > Check camera profile
   (offline) to validate an **owner-managed private** M33 JSON profile.
2. Select Calibration > Probe selected camera (explicit consent), choose the
   profile, and affirm the camera-only prompt. The probe must report actual
   frames from that source; camera-only success does not start projection.
3. Independently confirm actual Windows Extended displays and physically
   associate left/right output before any real Gray-code pattern display.
   The owner must power ON projectors at this separate stage.
4. Open Calibration > Capture Gray-code from camera...
5. Check **Use ONE private camera source profile**, then choose exactly one
   owner-managed profile. The USB camera index field is disabled in this mode.
   Without the checkbox the original index 0..15 flow remains unchanged.
6. Enter a **new, nonexistent** capture directory and physical projector X/Y.
   The final `I verified the physical projector...` checkbox still must be
   checked before OK is enabled. At OK the selected profile is checked
   **offline**, before camera or projector access. Invalid/unselected profile
   refuses the capture.
7. After confirmation, the existing `Session.capture_camera_scan` forwards
   that one profile to `capture_opencv`, which enforces the source-type and
   camera open/read timeout protections and records only the camera source
   **type** in its manifest. Camera frames are written only to the owner's
   new, authorized capture directory as part of the explicit optical run.
   There is no automatic camera discovery, no automatic projector power-on,
   no global camera profile caching, and no credential-bearing logs.

Keep the M33 profile outside Git and inside protected owner-managed storage;
never paste the camera password or stream URL into GitHub or the project UI
logs. The dialog displays only an anonymous *profile selected* state.
Backend exceptions are redacted when a private profile is used; failed
captures are not accepted as optical calibration.

## CI limits

New synthetic tests verify source choice, offline validation, original USB
index compatibility, no hardware before consent, safe recording of source
type without passwords, GUI wiring and backend failure redaction.

Synthetic CI cannot attest RTSP connectivity, raw fisheye mode, calibrated
intrinsic parameters, real projector origin, optical seam quality, latency
or native VIOSO7 `.sps` file parity. Physical QA remains tracked in
[Issue #67](https://github.com/kmjtechno/vioso-clone/issues/67).
