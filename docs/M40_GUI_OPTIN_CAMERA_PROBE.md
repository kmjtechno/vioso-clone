# M40 — Opt-in asynchronous camera-only GUI preflight

This milestone exposes the existing M36 bounded camera-frame diagnostic in
the Windows/PySide6 GUI. Use it with projectors **OFF**.

## Operator workflow

1. In the clone's GUI, select **Calibration > Probe selected camera
   (explicit consent)...**.
2. Choose an existing owner-managed M33 private camera source JSON file.
   The app validates its schema **offline** and displays only source type.
3. Read the prompt. Nothing opens a camera until **Yes** is explicitly
   selected (default is **No**). Clicking No ends the operation.
4. On Yes, a separate Qt worker samples **6 camera frames**, after **1 warmup**
   frame, from **only the selected source**. The main GUI remains responsive.
   The read-only summary shows resolution, exposure screening and hardware
   acceptance status. A warning is displayed for low light, high brightness
   or invalid camera connection.
5. To protect decoder/stream teardown, closing the application while a
   camera probe is running is refused; the window can be closed after the
   worker releases the selected camera stream.

## Data/safety boundary

- No projector patterns, fullscreen display windows, Windows display changes
  or real-time multi-output synchronization are performed.
- No captured frames, image files, URLs, usernames, passwords or private
  source paths are saved, printed in receipts, or written to project JSON.
- Unexpected OpenCV/SDK exceptions are replaced by generic messages; backend
  errors can contain private network URLs and are never shown in GUI dialogs.
- Only the explicit affirmative in-app user action starts camera access.
  A camera-source schema PASS alone never means the camera is online.
- This is bounded optical-input *screening*, not measured fisheye intrinsics,
  projector mapping, Gray-code accuracy, edge-blend quality, focus acceptance,
  frame synchronization or native VIOSO SPS compatibility.

The current P520 CodeBridge command allowlist does not include a camera probe:
this GUI capability is **not** a remote CodeBridge device action. It requires
a locally installed/current clone build with suitable camera drivers and
OpenCV decoder support. A private CP PLUS RTSP URL must be verified by the
owner locally; neither an IP address nor a stream path is inferred.

The owner should leave both physical projectors OFF until a separate
explicit physical calibration step is requested. Zero additional paid spend.
