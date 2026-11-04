# M36 — Camera-only frame probe while both projectors remain OFF

The owner's equipment is connected to Windows P520:
- One webcam
- CP PLUS CP-UNC-EE61L2C-VMD-Q network/PoE fisheye camera, currently powered on
- Two projectors physically connected but **powered OFF until the owner is asked to turn them ON**

M36 adds a **bounded, explicit-consent, camera-only diagnostic**. It is the missing live optical-input step between the M33 **offline** camera profile syntax validator and later projection-based Gray-code calibration.

## Sequence (local operator, no projector access)

First check an existing **owner-managed private** M33 source profile *offline*:

```text
vclone camera-profile-check E:/KMJ/Calibration/private-camera.json
```

To actually open **only that chosen camera**, the local operator must explicitly confirm:

```text
vclone camera-frame-probe E:/KMJ/Calibration/private-camera.json --confirm-camera --frames 8 --warmup 1
```

The command reads **4–16 frames**, optionally discarding **0–6 warmup frames**. It uses the current explicit M33 source backend (USB, RTSP, ONVIF-resolved RTSP, RTSP over TLS, MJPEG, replay, or a trusted registered SDK adapter). For network streams, the M33 FFmpeg/GStreamer backend enforces its four-second open/read timeouts where supported.

It prints a JSON receipt with camera type, frame dimensions, number observed, consistent-resolution gate, mean brightness, black/white clipping, Laplacian-based texture/sharpness *screening*, and a simple interframe change fraction. It **does not save frames, screenshots, camera URLs, credentials, network hostnames, source paths or device IDs**. It never opens a projector window, changes Windows displays or writes an output file.

A low-light scene returns `LOW_LIGHT_CHECK_EXPOSURE` and a nearly saturated white scene returns `HIGH_BRIGHTNESS_CHECK_EXPOSURE`. This is **screening evidence**, not camera auto-exposure adjustment, photometric calibration, measured absolute focus, optical alignment or projector acceptance. A still scene can legitimately return zero interframe changes, which is not automatically a camera failure.

## CP PLUS raw fisheye considerations

For **CP-UNC-EE61L2C-VMD-Q**, use the actual locally verified camera stream selected via its private profile. Do **not** guess its RTSP path; the IP address, ONVIF/RTSP login and passwords stay on the P520. Its original 2560×2560 fisheye main stream is within the maximum 8.85 MP capture budget. The decoder may require local FFmpeg H.264/H.265 support. Probe status is empirical: the source profile passing schema validation alone does not prove connectivity.

M32/M35 downstream fisheye calibration additionally requires a separately measured 12–48-view checkerboard intrinsic model and its exact matching **raw** fisheye stream resolution. Do not use a digitally dewarped panoramic camera view and silently apply raw fisheye lens coefficients.

## Safe physical test gate

M36 may be run while both projectors are OFF, but only from the operator's authorized P520 local command session or a newly approved, exact-profile CodeBridge camera-probe command. At the time of authoring, the existing CodeBridge project has **only `python_verify` and `rea_doctor` approved**, so the assistant cannot yet remotely open the physical camera using CodeBridge.

After an authorized live camera probe reports successful frame reads, the next gates are M34 desktop topology, real physical left/right projector display mapping, operator-confirmed exposure and raw fisheye intrinsics. At that point the owner can be told **once**, clearly, to power on both projectors for the separately confirmed sequential projector scan. There is no automatic hardware activation.

No proprietary VIOSO code, native SPS format or licensing routine is used or copied. No paid services required.
