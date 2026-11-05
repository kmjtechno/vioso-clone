# M52 — ONVIF Auto Detect, no username/password by default

The owner reports that their connected CP PLUS fisheye camera appears
automatically in ONVIF software without entering an ID or password.
**Discovery** and **video stream access** are distinct. ONVIF WS-Discovery
can advertise cameras on the local subnet without credentials; some cameras
also allow anonymous GetCapabilities/GetProfiles/GetStreamUri and RTSP, while
others require authentication. M52 supports the credential-free route
without disabling camera authentication or using default passwords.

## Use on P520 (projectors remain OFF)

1. Open the newest M52 portable GUI, after the Windows build is independently
   verified and published. Go to **Connect ONVIF Camera**.
2. Click **Auto Detect ONVIF Camera (no ID/password)**. This explicitly
   authorizes one short ONVIF WS-Discovery request to the local multicast
   address `239.255.255.250:3702`. Discovery is not run silently at startup.
3. If one private LAN camera replies, its IP/port/device-service path are
   filled in automatically. If multiple reply, select ONE. Neither step
   opens any video stream or configures the camera.
4. Leave **ONVIF username** and **ONVIF password** blank, tick the
   camera-only authorization checkbox and confirm the independent **Yes**
   dialog. The application makes an anonymous ONVIF Media1 request.
   If the device permits it, it resolves one raw-square profile's RTSP
   URL and samples six frames with existing OpenCV timeouts.
5. Only if your specific camera rejects anonymous access, optionally
   enter its authorized ONVIF user/password in the local dialog. There
   is no automatic guessed credential, password bypass or unsafe fallback.
6. The private on-screen receipt reports aggregate frame dimensions,
   exposure and frame count, not the stream URL, password, hardware ID or
   pixel content. Keep BOTH projectors OFF until camera-only QA passes.

Existing manually entered IP and manually entered credentials still work.
The source path advertised by WS-Discovery is used only after validating
the service address is private RFC1918 IPv4 and belongs to the exact host
that answered the multicast message. No arbitrary redirect, host-hop,
password-bearing URL, public-IP stream, camera settings write or filesystem
profile storage is allowed.

## Technical guardrails

- **Discovery opt-in only**, initiated by a click, not by opening the GUI.
- One multicast Probe, UDP 3702, IPv4 TTL 1, 1.5-second timeout, maximum
  32 received datagrams, 16 returned cameras, 16 KiB XML per response.
- No subnet brute-force scanning or common-password authentication attempts.
- WS-Discovery XML entities/DTDs refused, replies validated against sender.
- With both login fields empty: no WS-Security UsernameToken, no HTTP
  Digest auth handler, and no `:@` userinfo inserted in RTSP URLs.
- With both login fields present: existing WS-Security Digest and HTTP Digest
  handling remains unchanged. Mixed/partial credentials are refused.
- HTTPS uses OS certificate verification; no trust-all exception.
- Discovered device service path is validated before ONVIF HTTP, and stream
  endpoint still must remain on the selected camera's exact host.
- No camera is opened merely by discovery; full camera-only connection
  uses the existing two consent gates and bounded video capture pipeline.

**Real P520 CP PLUS behavior is NOT VERIFIED** by synthetic testing.
Firewall rules, VLAN segmentation, non-discoverable mode, ONVIF firmware,
RTSP authentication, H.265 decode and raw fisheye 1O calibration still
need actual camera-only owner testing. Vendor VIOSO 7 proprietary parity,
two-projector optical acceptance and signed release are separate milestones.

References:

- [ONVIF Core Specification](https://www.onvif.org/profiles/specifications/)
- [ONVIF Core Client WS-Discovery Tests](https://www.onvif.org/wp-content/uploads/2019/01/ONVIF_Core_Client_Test_Specification_18.12.pdf)
- [P520 optical/hardware acceptance tracker](https://github.com/kmjtechno/vioso-clone/issues/67)
