# M32 — Offline fisheye camera intrinsic calibration for P520

This is an **independent OpenCV fisheye model** for a wide-angle camera, such as a CP PLUS fisheye *if its exact model and output stream are compatible*. A webcam may instead use the existing `vclone.intrinsics` pinhole model.

**Camera model must be confirmed.** CP PLUS has multiple 5 MP/6 MP/12 MP fisheye network models, and a camera visible over a LAN/PoE connection is not necessarily available as a USB/DirectShow webcam. No camera connection, IP, RTSP URL or credentials are inferred or tested by this PR.

## Before you capture real photos

1. Measure a checkerboard's square size in millimeters. The default detector expects **9 horizontal by 6 vertical internal corners** (a 10×7-square board); change `--cols`/`--rows` when needed.
2. Use the camera's **raw native fisheye feed**, not a digitally dewarped, stitched, panoramic or cropped view. Lock focus, resolution and exposure/gain where possible.
3. Capture **12–48 sharp checkerboard images** at the **same exact resolution**, moving and tilting the board over the sensor field; include corners/edges and varied tilt. Avoid motion blur, glare and repeated identical views.
4. Place the photos in a new ordinary local folder. Do not include credentials or hidden camera configuration files. No need to turn on projectors for this offline lens-calibration step.

Example (paths and square size are illustrative, not auto-detected):

```
vclone fisheye-calibrate E:/KMJ/Calibration/fisheye-board-photos --cols 9 --rows 6 --square-mm 25 --max-rms-px 1.5
```

The command **does not open a camera, projector or network connection and writes no files**. It bounds photo counts/dimensions/file sizes, rejects linked inputs, requires every checkerboard to be detectable, checks spatial coverage, tilt diversity and reprojection RMS, and returns JSON on standard output.

Result schema: `kmj.fisheye.intrinsics.v1`, `lens_model=opencv_fisheye`, `camera_matrix`, `fisheye_distortion_k1_k2_k3_k4`, quality receipts, `hardware_acceptance=NOT_VERIFIED` and `native_vioso_sps_compatible=false`.

**Important:** Fisheye coefficients are in OpenCV's fisheye model and **cannot** be copied into a pinhole `CameraIntrinsics` `k1,k2,p1,p2,k3` array. The main Gray-code capture and geometric calibration pipeline still needs a separately qualified fisheye undistortion/mapping integration before this profile can be used to claim projector alignment.

## Hardware test plan (owner-operated)

- Webcam: first verify one live 2D flat-screen checkerboard calibration and unmasked/ROI scan as a baseline.
- CP PLUS fisheye: confirm exact model and whether connection is USB, ONVIF/RTSP/IP or HDMI capture device; test raw fisheye still-image export and this offline checkerboard calibration. Do **not** post camera passwords or RTSP URLs.
- Projectors 1 and 2: verify both appear as separately selectable displays with independently recorded pixel rectangles and resolutions. Confirm overlap region and camera coverage with the chosen camera before displaying patterns.
- Optical scan: acquire Gray-code frames one projector at a time with local operator confirmation and fixed camera exposure, then use M25/M28/M29 masks/quality checks. After geometry passes, test M14/M27 blend/color and M31 measured black levels. A software test cannot certify physical blend uniformity or synchronization.

Do not move or power projectors remotely without operator confirmation. Preserve existing P520 CodeBridge and OmniDesk agents, user calibration notes and the original vendor installation. No external paid provider is required.
