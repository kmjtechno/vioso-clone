# M48 — Explicit ONVIF Profile T Media2 read-only RTSP negotiation

M47 implemented authenticated **Profile S / Media1** GetCapabilities /
GetProfiles / GetStreamUri for an owner-selected RFC1918 camera. Some Profile T
cameras also expose a separate **Media2** service with a different SOAP
namespace and payload. M48 adds that read-media-only protocol, without
changing the working Media1 default or claiming full Profile T features.

## Private camera configuration

Existing M47 private camera JSON is unchanged. To use **Media2 only**, add:

\`\`\`json
"media_service": "media2"
\`\`\`

inside its existing \`"source"\` object. E.g. on the P520 owner-only profile:

\`\`\`json
{
  "schema": "kmj.camera.source.v1",
  "type": "onvif",
  "source": {
    "host": "192.168.1.50",
    "port": 80,
    "scheme": "http",
    "username": "ONVIF_ACCOUNT_ONLY_ON_P520",
    "password": "FILL_ONLY_ON_P520",
    "media_service": "media2"
  },
  "backend": "ffmpeg"
}
\`\`\`

The values are **placeholders**, not discovered settings. Never upload
credentials, IP configurations or a real private profile into Git or chat.
Use the same GUI **Check camera profile (offline)** and **Probe selected
camera (explicit consent)** actions. For Media2 the read-only handshake
on that ONE explicitly selected local camera is:

1. Device \`GetServices(IncludeCapability=false)\`: find exactly one service
   namespace \`http://www.onvif.org/ver20/media/wsdl\`; reject a missing,
   duplicate, remote-host or redirecting XAddr.
2. Media2 \`GetProfiles(Type=All)\`: parse bounded video-encoder resolution and
   tokens; by default require one unique largest-square fisheye candidate.
   If the user has already verified the intended raw stream token, its exact
   \`"profile_token"\` can be specified in the private JSON.
3. Media2 \`GetStreamUri(Protocol=RTSP, ProfileToken=...)\`: accept only one
   RTSP/RTSPS URI on the original exact private camera host and pass it to
   the existing OpenCV FFmpeg 4-second open/read timeout backend. Do not
   write credential-bearing URIs or images to logs or receipts.

There is **no automatic protocol fallback**: if Media2 fails the application
returns a safe error instead of trying Media1, public hosts, guessed RTSP
paths or unknown media configurations. Media1 remains the default when
\`media_service\` is missing or equals \`"media1"\`.

A square 2560×2560 video is only a *candidate* for original 1O fisheye,
not proof of genuine undistorted/raw optical geometry or reliable camera
driver compatibility. Confirm both raw fisheye mode and real frame quality
before owner-led intrinsics calibration.

## Tested and not tested

Linux/Windows synthetic tests verify namespaces, SOAP read-only operations,
service selection, profile dimensions, safe URI acceptance, private credentials,
lack of silent downgrade and no camera use in offline validation. There are
no physical CP PLUS camera frames or projected images in CI.

This does not implement ONVIF Profile T image settings, metadata, event
subscriptions, TLS certificate provisioning, recording Profile G, ONVIF
WS-Discovery scanning, PTZ, camera configuration writes, vendor-dewarp mode
switching, native VIOSO7 license or \`.sps\` parity.

**P520 real ONVIF credentials/firmware acceptance, raw 1O image-mode review,
fisheye geometric fit, two-projector scan/blend and Windows signing remain
NOT VERIFIED.** Track owner optical gates in [Issue #67](https://github.com/kmjtechno/vioso-clone/issues/67).

Reference specifications:
- https://www.onvif.org/specs/2512/ONVIF-Media2-Service-Spec-v2512.pdf
- https://www.onvif.org/specs/2506/ONVIF-Core-Spec-v2506.pdf
