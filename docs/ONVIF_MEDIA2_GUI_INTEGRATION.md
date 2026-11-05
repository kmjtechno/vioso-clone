# Optional ONVIF Media2 / Profile T (read-only)

This independent feature brings the older experimental Media2 pull request onto
current Calibration Studio without reverting M52 automatic discovery, M54
legacy CP PLUS authentication, M55 diagnostic codes, or M56 camera visual review.

## Owner workflow (P520, projectors OFF)

1. Open Calibration Studio → Connect ONVIF camera (no saved credentials).
2. Either explicitly click Auto Detect (bounded, local WS-Discovery), or enter
   the exact RFC1918 camera address and service port yourself.
3. Choose **Media1 / Profile S (default)** for existing CP PLUS behavior. Choose
   **Media2 / Profile T (explicit)** ONLY if the selected camera advertises
   ONVIF ver20 Media2. Optional credentials are entered only on the PC; enter
   username AND password or leave both empty when camera allows anonymous ONVIF.
4. Set the exact profile token if the correct raw/original fisheye stream is
   already known. Otherwise the Media2 branch selects only a uniquely largest
   square, encoder-backed bounded candidate. A square picture is not proof of
   raw optical geometry.
5. Confirm the dialog checkbox and independent Yes camera-only consent.
   Expect a maximum of six sampled frames and a non-exportable grayscale
   thumbnail on the local machine. No projector is powered or operated.
6. Keep the rig OFF until intrinsics, topology, Gray-code scan and dual-projector
   seam/blend acceptance are measured with the owner present.

## Protocol boundaries

- Media1 default remains GetCapabilities → GetProfiles → GetStreamUri.
  Legacy MediaProfile00000 connection-only fallback and optional credentialless
  ONVIF remain unchanged.
- Explicit Media2 uses Device GetServices(IncludeCapability=false) and requires
  exactly one ver20 Media2 endpoint on the same RFC1918 camera host. It issues
  Media2 GetProfiles(Type=All) then GetStreamUri(Protocol=RTSP,
  ProfileToken=...). This is **read-only media negotiation**, not full Profile T.
- Cross-host/redirect URLs, remote/private network escapes, unsupported schemes,
  missing encoder profiles, ambiguous raw candidates and invalid tokens fail
  closed. No silent fallback to another ONVIF version or guessed RTSP URL.
- TLS uses verified system trust and never falls back to insecure certificate
  handling. M54's narrowly gated HTTPS PasswordText retry remains; HTTP never
  gains this downgrade.
- No media credentials, private camera pixels, RTSP URLs or image frames are
  stored in project reports. Camera errors are mapped to existing fixed codes.

## Test scope and release limits

Synthetic tests exercise SOAP namespaces, service and profile selection,
same-host validation, absence of credential leaks, anonymous RTSP, opt-in GUI
selection and preserved Media1 default. These tests do **not** access a camera
or activate a projector. They cannot attest firmware-specific Media2 support.

Actual CP PLUS camera readout, raw fisheye mode, intrinsics, dual-projector
calibration, proprietary VIOSO 7 SPS interchange, synchronized output and
signed Windows packaging remain separate hardware/product gates in
[issue #67](https://github.com/kmjtechno/vioso-clone/issues/67).
