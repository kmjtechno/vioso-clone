# M59 — Present an actual calibrated still from Calibration Studio

M59 implements the missing GUI link between an existing **measured and
calibrated clone warp mesh** and a real desktop projector. Previously the
Studio could only preview warped content on its main canvas or export images.
The CLI had separate OpenCV presentation, but it was not usable from the
Studio workflow.

## Owner-operated acceptance flow

1. Calibrate a project from a real camera/Gray-code capture. Review the mesh.
   Save the independent clone JSON project. A UI camera probe alone does not
   create a projector calibration.
2. Switch Windows to **Extend** displays and physically identify the intended
   projector. Do not use Mirror/Duplicate mode.
3. With the projector powered on by the owner, choose **Present Still** in the
   Studio toolbar (also in Calibration menu). The selector lists only secondary
   non-overlapping, bounded screen rectangles; the primary desktop is refused.
4. Choose the real target and a 1–10 second duration. Check the explicit
   screen/output authorization. The form does not contact a camera or projector.
5. Select the local image. At the **separate final Yes dialog**, verify the
   actual screen dimensions and projector power/mapping. No is the default.
6. The app renders with the project's **actual calibrated mesh** and refuses
   if the warped BGR image resolution is not identical to the selected Qt
   screen's logical desktop geometry. The window is a dedicated frameless Qt
   fullscreen timed output on the selected screen; Escape cancels early.
7. Review geometry, focus and alignment physically. A working window is NOT
   evidence of true optical calibration, lens fit, brightness/color parity,
   multi-projector synchronization or compatibility with native VIOSO 7.

## Safety and implementation

- No output before both consent gates, a real software warp mesh, a content
  file and a validated distinct non-primary Extended display. Mirrored
  displays or overlapping screen rectangles are ineligible.
- No automatic projector power-on, camera opening, desktop reconfiguration,
  network activity, generated output PNG or project overwrite occurs.
- The same strict screen and output dimensions are rechecked immediately
  before fullscreen presentation to fail closed after hot-unplug.
- Output is bounded 1–10 seconds, 1920×1080 maximum, one projector only.
  The application does not change Windows scaling. When Qt logical geometry
  differs from the calibrated native resolution (e.g. DPI scaling), it refuses
  rather than distort the warp; verify correct 100% scaling and project sizes.
- Projector output uses Qt GUI-thread display rather than OpenCV windows;
  test coverage uses only synthetic frames and fake screen rectangles.
- The result remains `hardware_optical_acceptance=NOT_VERIFIED`, even
  when a timed presentation is attempted.

## Remaining product gates

The clone still needs verified CP PLUS/raw fisheye acquisition, checkerboard
intrinsics, real per-projector Gray-code capture and calibration, measured
two-projector stitching/seam and calibrated multi-display playback.
High-frame-rate GPU output, NDI, 3D/dome workflows, signed Windows installer,
and proprietary VIOSO 7 SPS interchange are **not implemented/verified**.
See [hardware gate issue](https://github.com/kmjtechno/vioso-clone/issues/67).

This is a functional incremental independent implementation with no paid
service and no third-party vendor code.
