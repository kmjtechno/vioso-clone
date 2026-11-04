# M34 — P520 dual-projector rig preflight (NO projector power required)

This feature is intended for the owner's known setup:
- Windows P520 with one local webcam
- CP PLUS CP-UNC-EE61L2C-VMD-Q PoE/network fisheye camera (already ON)
- Two physically connected projectors, which the owner may leave OFF until instructed

## What M34 can actually verify

`vclone rig-preflight --expected-projectors 2` calls only the official, read-only Windows `EnumDisplayMonitors`/`GetMonitorInfoW` APIs and reports the current interactive desktop's display rectangles, pixel dimensions, primary flag and any overlapping/mirrored rectangles. It does not call Windows display-mode modification APIs. It does **not** open windows, start a projector, access cameras, change display modes or make any network connection.

An optional owner-local private camera JSON profile (see M33) can be syntax-checked with no device access:

    vclone rig-preflight --expected-projectors 2 --camera-profile E:/KMJ/Calibration/camera-profile.json

**Do not send stream URLs, device passwords or full profile contents in chat.** The result includes only non-identifying profile type/status, never source, URI, IP or credentials.

The intended safe output for 1 desktop + 2 extended displays is `display_layout_gate=OPERATOR_MAPPING_REQUIRED`, **not** automatic proof the projectors are powered or mapped. `desktop_displays_found >= 3` means only that Windows reports enough extended rectangles at that moment. If both projectors are OFF, Windows may report zero, one or two available screens depending on the graphics output, EDID and monitor electronics.

Overlapping/mirrored Windows displays are refused for independent two-projector calibration because two distinct physical outputs cannot safely be inferred from identical coordinates.

## Hardware activation gate

**Keep the projectors OFF until the operator confirms a real calibration session.** After the current GitHub main is safely available on P520 (without resetting or cleaning existing owner research notes), run the read-only rig preflight first. If it cannot map both projectors while they are off, the next physical step can be asking the owner once to turn both projectors ON, then repeat the read-only Windows layout probe. Do not display Gray-code frames until:

1. The operator has physically confirmed two separate projector display rectangles and their left/right projector identity.
2. The selected camera source (webcam or CP PLUS RTSP stream) has been separately tested to deliver usable raw frames.
3. Projector resolution, screen position, camera field-of-view and intended scan region have been confirmed.
4. The output path is new and the existing `capture-graycode --confirm-display` gate is explicitly satisfied.

No camera or display is powered remotely by this feature. Projector-power state, physical identity, actual camera stream, geometry and calibration remain `NOT_VERIFIED`. The CodeBridge P520 approved command list currently includes software test and offline REA doctor only; it does not authorize arbitrary PowerShell or hardware inventory execution. Add an explicit approved read-only P520 diagnostic profile or run the program manually in the correct interactive Windows desktop session when hardware QA is scheduled.

Microsoft Win32 references:
- https://learn.microsoft.com/en-us/windows/win32/gdi/enumeration-and-display-control
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumdisplaymonitors
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getmonitorinfow

This is an independently authored test harness, not native VIOSO 7 interoperability or projector certification.
