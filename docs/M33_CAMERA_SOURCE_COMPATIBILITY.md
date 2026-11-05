# M33 — Camera-agnostic optical acquisition: webcam, IP/RTSP/ONVIF and SDK bridge

The VIOSO Clone must **not** be tied to a camera brand. This implementation introduces an **explicit, extensible input contract** for the existing M8/M29 Gray-code capture workflow. Camera support means the source supplies readable OpenCV BGR/BGRA/grayscale frames within the capture pixel budget, not guaranteed driver/hardware compatibility.

## Verified CP PLUS reference

The owner's **CP-UNC-EE61L2C-VMD-Q** is a **network/PoE 6MP fisheye** camera, not a USB webcam. CP PLUS officially lists 2560×2560 main-stream image size, 185-degree view, 1.68mm fixed lens, triple streams and H.264/H.265/MJPEG. The specific unit's working RTSP/ONVIF address, firmware, authentication, and raw 1O stream mode must be obtained locally: **do not guess a manufacturer RTSP URI or send passwords in chat.**

- Manufacturer: https://cpplusworld.com/cp-unc-ee61l2c-vmd-q
- ONVIF streaming contract: https://www.onvif.org/profiles/profile-s/

**Choose the original/raw fisheye view** rather than a dewarped 2P/4R panoramic or split view before running M32 lens intrinsics, or the lens calibration may be invalid.

## Supported camera-source contracts

| type | Input | Adapter/runtime requirements |
|---|---|---|
| `usb` | Numeric index 0..15 | UVC webcam, USB capture card, HDMI camera bridge; platform OpenCV backend `auto/dshow/msmf/gstreamer` |
| `rtsp` | Explicit `rtsp://` URI | FFmpeg/GStreamer backend; bounded open/read timeouts |
| `rtsps` | Explicit `rtsps://` URI | Camera and OpenCV transport must actually support encrypted RTSP |
| `onvif_rtsp` | RTSP stream URI obtained from a trusted ONVIF client | Same RTSP decoder; this does **not** implement ONVIF discovery or credentials retrieval |
| `http_mjpeg`, `https_mjpeg` | Explicit HTTP(S) MJPEG video-stream URI | FFmpeg/GStreamer and compatible stream codec |
| `video_file` | Existing absolute video-file path | Offline replay without a camera; safe non-symlink regular file |
| `sdk` | Exact installed adapter ID | A **trusted, registered Python factory** bridging a specific supported GenICam/industrial/DSLR SDK to a `VideoCapture`-like read/grab/release object |

These cover interface classes, **not every make/model automatically**. Proprietary SDK cameras require implementing and qualifying their own trusted adapters; FireWire, specialized global-shutter industrial cameras, NDI, etc. are not claimed working without testing.

## Private local profile

Write an owner-managed local file `E:/KMJ/Calibration/camera-profile.json` (example only; real RTSP location is device-specific):

```json
{
  "schema": "kmj.camera.source.v1",
  "type": "onvif_rtsp",
  "source": "rtsp://your-camera-host/your-onvif-returned-stream",
  "backend": "ffmpeg"
}
```

For USB webcam use `"type": "usb", "source": 0, "backend": "auto"`. Use `"type": "rtsp"` instead of `onvif_rtsp` for ordinary manually configured RTSP. The CP PLUS specific **stream path is not verified** by these examples. Protect the local profile with your Windows owner account permissions if you use authenticated URLs; never put the file in the Git repository, paste credentials into chat, or pass credentials directly as CLI arguments. Camera profiles and stream URIs are never included in generated capture receipts or camera-profile-check JSON.

First run an **offline, no-connection preflight**:

```
vclone camera-profile-check E:/KMJ/Calibration/camera-profile.json
```

It checks schema, source type, backend compatibility, URI syntax or local file constraints, but **does not** probe hardware, LAN, login, codecs, exposure or actual frame quality. A valid profile is not evidence of an online camera.

Then, after explicitly choosing the camera, projector screen coordinates, exposure and a **new** capture directory, the local operator can run:

```
vclone capture-graycode --width 1280 --height 800 \
  --camera-profile E:/KMJ/Calibration/camera-profile.json \
  --projector-x 1920 --projector-y 0 --out E:/KMJ/Captures/session-new \
  --confirm-display
```

**All projector coordinates and file paths above are illustrative only**. Captures never auto-start on connecting a camera, and `--confirm-display` is still mandatory. Existing `--camera 0` USB capture is backwards-compatible.

## Physical acceptance, not supported by CI alone

For the user's **1 webcam, 1 CP PLUS fisheye and 2 projectors**: identify local Windows display rectangles and camera stream availability; photograph a 9×6 internal-corner board at locked resolution/controlled illumination; run M32 fisheye checkerboard solver; use separate M25/M28 camera ROI and M29 projector masks; capture one projector at a time; quantify geometry/overlap/blacklevel; then display both optical previews only after operator confirmation.

- Native 2560×2560 fisheye camera frames now pass the 8.85MP total camera pixel safety budget across capture, masked capture-check and black-level diagnostics.
- **No intrinsic-calibration auto-switch** is implemented merely from a camera model name; raw fisheye distortion/undistortion integration must be measured, not guessed.
- RTSP codecs, GPU decoding, ONVIF authentication, camera-specific API and latency/synchronization quality depend on local equipment/software. These still need hardware evidence.
- No native VIOSO7 calibration format parity, automatically supported SDK, physical projector certification, frame lock or fully validated commercial release is claimed.


## M47 native ONVIF Media1 resolution (new)

New camera profile \`type: "onvif"\` accepts a private source record
(\`host\`, \`port\`, \`scheme\`, \`username\`, \`password\`, optional
\`profile_token\`) and performs actual authenticated ONVIF Profile S Media1
GetCapabilities / GetProfiles / GetStreamUri after a local camera-only
confirmation. This is different from legacy \`onvif_rtsp\`, which only validates
an already known \`rtsp://\` address. It never scans the LAN or guesses an
RTSP route. For CP PLUS setup, examples and limitations, see
[M47 ONVIF guide](M47_ONVIF_CPPLUS_MEDIA1.md).
