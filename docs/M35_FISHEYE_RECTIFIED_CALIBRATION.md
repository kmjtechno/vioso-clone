# M35 — Fisheye rectification integrated with Gray-code calibration

The owner's CP PLUS CP-UNC-EE61L2C-VMD-Q is a network fisheye camera. M32 can fit an independently implemented OpenCV fisheye model from **raw**, native-resolution checkerboard photos. **M35 now makes that fitted model usable in the clone's actual optical Gray-code scan workflow.**

This is opt-in mathematical image rectification, **not** a claim of native VIOSO 7 `.sps` compatibility, factory CP PLUS lens-profile compatibility, real projected geometry acceptance or automatic multi-projector synchronization.

## Workflow before projectors are turned on

1. Collect 12–48 clear checkerboard photos from the **raw, non-dewarped fisheye stream** at exactly the future scan resolution. Use M32 `fisheye-calibrate`, then save its returned stdout JSON **locally** into an owner-controlled file such as `fisheye-model.json`. Never share private camera URIs, credentials or the camera source profile.
2. An M32 model must have the correct `kmj.fisheye.intrinsics.v1` schema, `opencv_fisheye` lens type, 12–48 views, finite focal length/camera principal point and four native fisheye coefficients. M35 refuses a pinhole distortion profile, invalid numbers, oversized/symlink profiles or mismatched image dimensions.
3. Inspect a **new** rectified virtual-pinhole preview of a recorded grayscale frame:

   ```
   vclone fisheye-rectify-preview E:/KMJ/Captures/run001/p00.png E:/KMJ/Captures/run001/fisheye-model.json E:/KMJ/Captures/run001/preview-rectified.png
   ```

   This is an **exclusive-create** PNG export. The input frame, capture manifest, model profile, owner work and any existing output cannot be overwritten. Edge borders may be black where raw sensor coordinates fall outside the valid rectified field.

4. Screen the full recorded Gray-code scan using the same profile, **without writing any frame**:

   ```
   vclone capture-check E:/KMJ/Captures/run001 --fisheye-profile E:/KMJ/Captures/run001/fisheye-model.json --fisheye-balance 0.25
   ```

   If a camera ROI mask exists, add `--camera-mask E:/KMJ/Captures/run001/camera-roi.png`. The M28 black-included/white-excluded camera mask is selected in **raw fisheye camera coordinates**, then remapped using nearest-neighbor interpolation. Valid decoded pixels are measured only inside the intersection of rectified sensor coverage and optional camera ROI.

5. For actual `Calibrate`, set the following extra clone project `scan` fields (your usual fields remain required):

   ```json
   {
     "fisheye_profile": "fisheye-model.json",
     "fisheye_balance": 0.25,
     "camera_mask": "camera-roi.png"
   }
   ```

   The `fisheye_profile` must be a **basename within the scan folder**, never a separate absolute or traversal path. The optional `camera_mask` is likewise a basename inside that folder. **`scan.cam_corners` must be measured in the rectified virtual-pinhole image** (for example from a preview above), not the original raw fisheye image. Mixing these two coordinate systems produces invalid geometry.

6. Two projectors require **separate sequential** capture/geometry validation; they must not both show calibration Gray-code patterns simultaneously. Physically measure blend geometry, overspill, black level and color match after both scans pass.

## Safety and feature limits

- Opt-in only: without `fisheye_profile`, original webcam/raw Gray-code calibration and capture-check stay unchanged.
- `fisheye_balance` stays in 0..1; output image size remains the original sensor resolution and bounded total pixels.
- Source images and calibration JSON are read-only. M35 uses OpenCV `fisheye.estimateNewCameraMatrixForUndistortRectify` and `initUndistortRectifyMap`, then `remap`. No camera, network, projector or Windows display is opened by these commands.
- A precomputed model is **not** automatically inferred from camera brand or serial; its validity for the exact CP PLUS lens, raw video mode, focus and stream must be measured.
- This model is not appropriate for panoramic/dewarped CP PLUS modes or a normal pinhole webcam. The exact CP PLUS RTSP stream endpoint remains owner-local and unverified.
- The reported `software_capture_quality=PASS` is screening evidence, **not physical calibration certification**. Live calibration requires the owner's explicit local projector-on instruction after safe display and camera checks. Both projectors should remain OFF until that stage.
