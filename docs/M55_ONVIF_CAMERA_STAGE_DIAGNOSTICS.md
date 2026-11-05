# M55 — Camera probe failure-stage diagnostics (no credential exposure)

Owner screenshots from P520 show the dark Calibration Studio starts, but the
Camera Source card says `PROBE FAILED · NOT VERIFIED`, with session activity
only `camera-only frame probe failed`. That result does **not** identify
whether the selected CP PLUS ONVIF camera was rejected at login, media service,
profile selection, RTSP transport/decoder, or frame acquisition. No other
specific cause can be inferred from the screenshot.

## What M55 changes

The existing owner-confirmed, camera-only probe now reports one allowlisted
**stage code** in the warning dialog and session activity, with a short
actionable explanation; it still never exposes a camera address, video URL,
username, password, serial, or native exception text. Windows title contains
`M55 camera diagnostics` so the owner can tell this build apart from the
earlier M51/M54 graphical alpha. Existing File/Calibration controls and the
three hardware status cards remain unchanged.

| Code | Meaning and recommended next check |
| --- | --- |
| `PROFILE_INVALID` | Private camera selection or source fields invalid; correct IP/port or both account fields |
| `ONVIF_AUTH_REJECTED` | Camera explicitly refused ONVIF login. V2.5 previously used a cached secure-profile account, **not** necessarily anonymous access |
| `ONVIF_CONTROL_UNREACHABLE_OR_TLS` | ONVIF request failed before a usable SOAP response: local port, reachability, or verified HTTPS certificate |
| `ONVIF_PROFILE_SELECTION_FAILED` | No acceptable unique raw-square profile or allowed legacy MediaProfile00000 candidate |
| `ONVIF_STREAM_URI_UNAVAILABLE` | ONVIF media response lacked a safe RTSP stream URI |
| `ONVIF_NEGOTIATION_FAILED` | Other ONVIF protocol or endpoint mismatch |
| `RTSP_DECODER_OPEN_FAILED` | ONVIF URI resolved but local FFmpeg/OpenCV couldn't open the RTSP stream |
| `RTSP_TIMEOUT_UNAVAILABLE` | Required bounded OpenCV network timeouts not available |
| `CAMERA_WARMUP_FAILED` | Frame stream opened but warmup frame not available |
| `CAMERA_FRAME_READ_FAILED` | Stream opened but bounded set of six frames couldn't be read |
| `CAMERA_FRAME_FORMAT_INVALID` | Unexpected frame pixel format, dimensions or memory limits |
| `CAMERA_PROBE_FAILED` | Other internal error; message deliberately sanitized |

Errors are fixed codes, **not** raw exception messages. Any unrecognized
plugin/native exception is reduced to the generic safe code. This avoids
leaking RTSP URLs that often contain usernames/passwords.

The app remains camera-only until two explicit user confirmations; no
projector output, camera settings changes, LAN sweep, saved pixel data or
new credential migration. This update does **not** automatically unlock
the V2.5 app's proprietary secure credential cache.

## What to do with a real CP PLUS camera

On P520 use the new verified M55 Windows prerelease:

1. Close the previous VIOSO Clone EXE, extract M55 ZIP to a fresh folder, run
   the new executable. Its title must contain `M55 camera diagnostics`.
2. Choose **Connect ONVIF Camera** → **Auto Detect** and select your
   private-LAN CP PLUS camera. Use an exact local ONVIF account only if
   this camera does not permit anonymous media. No password should be
   sent through GitHub, this chat or screenshots.
3. Approve the two explicit camera-only confirmations. Leave both connected
   projectors **OFF**.
4. If the camera fails, share only the fixed **Diagnostic code** from the
   warning dialog, never the login, IP or stream URI. Then we can target
   the actual ONVIF step rather than guessing.
5. A six-frame report is only video reception; real raw-1O fisheye geometry,
   intrinsics, physical projector mapping and edge-blend acceptance are still
   separate operator-led gates.

Source tests cover category propagation, secret-shaped native error
redaction, positive safe dialog messaging, no network before consent,
stream cleanup, and old Windows alpha GUI self-tests. Actual camera
hardware is **NOT VERIFIED** by GitHub CI.

[Hardware tracker](https://github.com/kmjtechno/vioso-clone/issues/67).
