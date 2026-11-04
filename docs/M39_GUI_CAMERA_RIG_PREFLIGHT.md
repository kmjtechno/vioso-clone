# M39 — P520 GUI camera source and display rig preflight

This small GUI milestone makes the existing M33 and M34 **read-only** checks
accessible without hand-writing commands. Both projector outputs can remain
powered **OFF** throughout these checks. No vendor VIOSO binaries or licensing
materials are used.

## Camera profile — offline only

Select **Calibration > Check camera profile (offline)...** and choose your own
private M33 JSON source profile. The application validates source class,
bounded schema and capture backend without opening a camera, network socket,
RTSP stream or projector. It displays only the safe source type and backend.

For CP PLUS CP-UNC-EE61L2C-VMD-Q, the locally verified RTSP/ONVIF source URL
and any passwords remain in an owner-managed local profile; never commit this
file or paste credentials into a chat. This feature does not discover the
camera's RTSP URL or claim compatibility until actual frame reads succeed.
Other USB/UVC, network and trusted SDK camera classes use the same independent
M33 profile model, subject to installed backends and adapters.

## Windows display topology — read-only

Select **Calibration > Check Windows projector rig (read-only)...**. It uses
Win32 desktop-monitor enumeration through the M34 checker (only supported in
an interactive Windows desktop session). Default expectation is two projectors
plus the primary desktop. It displays rectangles and a gate:

- OPERATOR_MAPPING_REQUIRED — enough distinct non-overlapping rectangles;
  you must still confirm which physical projector corresponds to each one
- BLOCKED_INSUFFICIENT_EXTENDED_DESKTOPS — Windows does not expose enough
  independent desktops in this session; projectors may be off
- BLOCKED_MIRRORED_OR_OVERLAPPING_DESKTOPS — insufficient distinct mapping

The output deliberately does not infer projector power, serial number,
physical alignment or which rectangles represent the two projectors. A valid
desktop layout is **not** verified optical calibration. The GUI never changes
Windows display mode, opens a camera, sends projected patterns, modifies the
currently loaded project or creates capture files.

## What this does not finish

M36 camera-frame-probe still requires a separate explicit user confirmation
and a configured local source; it is **not automatically started** by M39.
Real left/right sequential Gray-code optical captures, CP PLUS fisheye
intrinsics, photometric blend validation, native VIOSO SPS interoperability
and signed Windows installation remain **NOT VERIFIED**.

The owner's P520 CodeBridge currently has only python_verify and rea_doctor
approved command profiles. No remote camera/rig command is implied by this
GUI feature. No additional paid provider is required.
