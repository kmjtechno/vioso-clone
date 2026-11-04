# M30 — Independent marker-based 3D camera pose estimation

VIOSO 7 publicly documents a marker-based initial camera-pose estimation step in its 3D workflow: https://docs.vioso.com/calibration/content-mapping/3d-mapping/camera-pose-estimation-in-vioso-7

This clean-room module reproduces the **general mathematical capability** with OpenCV PnP and reprojection quality gates, not any vendor algorithm, native marker file, calibrated model or proprietary camera output.

## Input

Use an **owner-measured** UTF-8 JSON file (64 KiB maximum), an existing regular file:

```json
{
  "schema": "kmj.camera-pose.markers.v1",
  "world_units": "mm",
  "image_size": [1280, 720],
  "intrinsics": {
    "fx": 900.0,
    "fy": 895.0,
    "cx": 640.0,
    "cy": 360.0,
    "distortion": [0, 0, 0, 0, 0]
  },
  "markers": [
    {"world": [0, 0, 0], "image": [640, 360]}
  ]
}
```

The single marker above **is an illustration of the field structure, not enough for a pose solution**. Provide **6–128 independently measured, well-distributed, non-coplanar 3D points** with corresponding 2D pixels in the camera image. World units must be `mm` or `m`. Intrinsic focal lengths and principal point must be measured/verified for the exact camera resolution and lens. Distortion order is OpenCV `[k1,k2,p1,p2,k3]`.

## Command

    vclone estimate-camera-pose E:/KMJ/Captures/markers.json --max-rms-px 1.5 --min-inlier-fraction 0.70

The command opens no cameras, windows or projectors and writes no files. It uses OpenCV EPnP RANSAC followed by LM refinement where available, rejects duplicate/degenerate markers, excessive outliers, points behind camera and high reprojection RMS, then returns a JSON **world-to-camera** rotation vector/matrix and translation, camera center in world coordinates and precise inlier/error evidence.

A mathematically passing pose is an **initial estimate** only. It is not proof that the physical camera/3D model are aligned: real projection test markers, lens distortion, exposure, camera rigidity and measured projector geometry need physical QA. It is not a native VIOSO 7 project/SPSet/.sps format converter.
