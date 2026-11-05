# M47 — ONVIF Media1 for CP PLUS and other private-LAN IP cameras

This adds actual ONVIF control-plane communication to the independent clone.
Previously, type \`onvif_rtsp\` only accepted an RTSP URL already discovered
by another tool. New type **\`onvif\`** performs Media1 SOAP read-only
GetCapabilities -> GetProfiles -> GetStreamUri using the ONVIF device's
existing account, then passes the returned RTSP URL to the same bounded OpenCV
FFmpeg capture stack used by the camera-only probe and confirmed Gray-code GUI.

## Device facts and limitations

The owner's **CP-UNC-EE61L2C-VMD-Q** manufacturer's spec lists ONVIF
Profiles S/G/T, 2560 × 2560 6MP original fisheye 1O output and H.265/H.264
codecs. M47 uses **ONVIF Profile S / Media1** for retrieving video URIs,
not Profile G recorded playback, Media2/Profile T advanced controls, PTZ,
WS-Discovery network scans, vendor dewarp configuration or lens coefficients.

Reference: https://cpplusworld.com/cp-unc-ee61l2c-vmd-q
ONVIF Media1: https://www.onvif.org/specs/srv/media/ONVIF-Media-Service-Spec-v240.pdf

## Private profile — create only on P520, outside source control

In an owner-restricted directory such as \`E:\KMJ\Calibration\private\`,
create \`cp-plus-onvif.json\`. Do not send this file or its password to chat.

\`\`\`json
{
  "schema": "kmj.camera.source.v1",
  "type": "onvif",
  "source": {
    "host": "192.168.1.50",
    "port": 80,
    "scheme": "http",
    "username": "local-onvif-operator",
    "password": "FILL_ON_P520_ONLY"
  },
  "backend": "ffmpeg"
}
\`\`\`

**All network values above are placeholders**, not inferred camera settings.
The camera must have ONVIF enabled and a valid read-media ONVIF account.
Do not paste your actual ONVIF password or address into the repository. Prefer
camera HTTPS with a trusted certificate whenever supported. HTTP is only
accepted with an explicitly supplied RFC1918 private IPv4 camera address,
never a public host; WS-Security UsernameToken PasswordDigest and HTTP
Digest challenge support are used. If media XAddr or RTSP URL points at a
different host, redirects, DTDs/entities or unbounded SOAP bodies, resolution
is rejected rather than silently connecting elsewhere.

For default selection, the app chooses the **unique largest square
Media1 video profile**, avoiding an ordinary 1920×1080 panoramic stream.
A square resolution **does not prove raw optical geometry**. You must
visually verify the camera is in original/raw 1O mode before measuring
fisheye intrinsics. On cameras with multiple equally large square profiles
or no square profile, add \`"profile_token": "ACTUAL_ONVIF_TOKEN"\` inside the
private source record; there is no automatic guessing or config-changing.
This is the opaque token returned by the camera, not the profile name.

## Ordered local tests (projectors OFF)

1. Select **Calibration > Check camera profile (offline)** and choose the
   JSON file. This reads/validates the profile without opening any camera
   or network connection. A PASS does not establish hardware compatibility.
2. Select **Calibration > Probe selected camera (explicit consent)** and
   choose that same file. Read the camera-only prompt and affirm Yes. The
   new ONVIF Media1 resolution then occurs for that selected camera only.
   The source is decoded and 6 frames screened in aggregate; no pixels,
   account credentials, ONVIF hosts, native stream URLs or private paths are
   written to the report. Both projectors stay OFF.
3. Confirm the retrieved stream's actual raw 2560×2560 resolution (or the
   device's configured native mode) and observe expected original fisheye
   imagery. If native codec/H.265 cannot be decoded by the installed
   FFmpeg/OpenCV, select an explicitly configured H.264 profile on the camera
   or investigate local codecs. No decoder fallback invents RTSP paths.
4. Later, only after owner power-on approval, run the same profile in
   **Calibration > Capture Gray-code from camera...**. Explicit physical
   projector mapping and a new capture directory are still required.
   Perform one projector at a time; evaluate M25 integrity and M37/M38 seam.
   Camera power and local ONVIF read permission do **not** imply projector
   power or physical optical acceptance.

CLI option (same explicit camera-only consent):
\`\`\`text
vclone camera-profile-check E:/KMJ/Calibration/private/cp-plus-onvif.json
vclone camera-frame-probe E:/KMJ/Calibration/private/cp-plus-onvif.json --confirm-camera --frames 8
\`\`\`

Never create/paste credential-bearing command-line URLs. No auto-scanning,
remote login, firmware changes, account creation, ONVIF discovery broadcast
or projector action occurs as part of installing this capability.

## Verified scope vs still pending

Mocked regression verifies Media1 SOAP sequencing, per-request WSSE digest,
HTTP Digest availability, bounded responses, exact-host enforcement, preference
for square original stream, password redaction, explicit confirmation,
integration into the existing FFmpeg timeout controls and offline profile
validation. Real P520 CP PLUS RTSP, camera credentials, ONVIF firmware/auth
quirks, true raw 1O output, fisheye intrinsics, dual projector optical quality,
native proprietary VIOSO7 SPS parity and Authenticode signing remain
**NOT VERIFIED** until operator-held receipts prove otherwise. See issue #67.
