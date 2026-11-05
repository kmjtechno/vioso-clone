# M49 — One-time ONVIF camera connection from the GUI (no password file)

M47 introduced the real ONVIF Profile S / Media1 read-only camera flow.
M49 adds a GUI path so the owner can test a CP PLUS or compatible private-LAN
ONVIF camera **without first saving a credential-bearing JSON profile**.

## Camera-only P520 acceptance (both projectors OFF)

In the new M49 Windows build, open the GUI and select:

**Calibration > Connect ONVIF camera (no saved credentials)...**

Enter the camera's actual private IPv4 (not a guessed address), ONVIF service
port, HTTP/verified HTTPS choice, ONVIF read-only username and password. Leave
profile token blank unless the camera's real raw fisheye token is known.

The password field is hidden. This flow requires both:

1. Ticking **I authorize one camera-only ONVIF/RTSP probe** to enable OK.
2. A second **Yes** confirmation before any network or camera access.

The control profile is validated offline before either camera or projector
operations. Only that selected ONVIF endpoint may be contacted. The app
requests ONVIF Media1 GetCapabilities -> GetProfiles -> GetStreamUri, then
attempts six bounded video frames with one warmup frame. Neither image pixels
nor ONVIF credentials are saved to disk or application project logs. The
visible report contains only aggregate dimensions, frame count and exposure
screening. The dialog's private profile is discarded after the probe.

The independent original private JSON camera profile remains available for
later projector Gray-code capture; M49 does not automatically configure or
start projection. Both connected projectors should remain OFF for this probe.

A successful camera probe is **not** 100% hardware acceptance. The operator
must still verify that a 2560x2560 (or exact configured native size) CP PLUS
stream is original/raw 1O fisheye rather than dewarped, run intrinsics from
physical checkerboard frames, explicitly turn on both projectors after the
camera stage, and inspect mapped projector geometry, seam/blend and color.

## Design/security guards

- No background WS-Discovery, LAN broadcast, device census or default login.
- Reject non-RFC1918 hosts; reject cross-host ONVIF/RTSP XAddr and redirects.
- HTTPS defaults to OS trust validation; self-signed camera TLS certificates
  are not silently accepted.
- No ambient Windows `HTTP_PROXY`/`HTTPS_PROXY`: direct LAN connection
  only, with four-second ONVIF request timeout.
- Credentials remain process memory only for this dialog and worker lifetime,
  then are released. No project state, URL, screenshots, log output or report
  includes the account or password. On-disk paging/memory snapshots are
  outside what a Python application can independently guarantee.
- M49 tests are synthetic/offscreen only and do **not** prove the owner's
  CP PLUS firmware response, account rights or frame decoding.
- The original CLI `camera-frame-probe <private JSON> --confirm-camera`
  and existing confirmed optical capture remain backward compatible.

Projectors ON is a separate, explicitly owner-controlled physical step.

Sources: [ONVIF setup](M47_ONVIF_CPPLUS_MEDIA1.md),
[Hardware acceptance tracker](https://github.com/kmjtechno/vioso-clone/issues/67).
