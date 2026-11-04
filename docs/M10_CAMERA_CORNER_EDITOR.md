# M10 — Camera Corner Editor (independent project workflow)

This milestone adds a GUI workflow for creating a calibrated clone-format JSON project from a captured camera image. It does **not** load native VIOSO 7 .sps files or validate real projector calibration.

## User steps

1. Launch the app: `python -m vclone gui` (requires PySide6).
2. Use **Calibration → Setup capture folder and dimensions**.
3. Select the folder containing M8 `p00.png`/`n00.png` captures. Enter projector dimensions and intended content resolution. If capture_manifest.json is present, its schema and projector size are checked against the entered dimensions.
4. Use **Calibration → Select camera corners**. The editor opens `p00.png` and accepts clicks in the order **top-left → top-right → bottom-right → bottom-left**. Undo/Clear let the operator correct mistakes. The editor rejects nonconvex, reversed, out-of-bounds or near-zero-area quadrilaterals.
5. Confirm. The project stores `scan.cam_corners`, `scan.content_corners`, `camera_size` and the reference image basename. It automatically derives content corners from resolution. Save to a **new clone JSON project** through File → Save As. The camera capture image is never changed.
6. After verifying correspondence visually, run `Calibrate` from the GUI, followed by `Export` or the existing preview CLI. Mistaken corner selection can yield a distorted mesh even when syntactically valid.

**Important:** Changing the scan folder/resolution or camera corner coordinates invalidates previously calculated calibration data, edit/export state and the mesh. This avoids applying stale geometry to a new capture.

## Safety / evidence

- The GUI never opens a camera or projector when merely editing corners.
- Input file must be a regular, non-symlinked `p00.png` within 32 MiB; decoder image dimensions are bounded to 4096×2160. JSON capture manifests are capped at 64 KiB.
- A capture can be viewed and its dimensions selected, but real lens distortion, user click precision, camera exposure and physical projector output still need a controlled P520 hardware acceptance.
- Synthetic geometry and PySide6 offscreen tests prove model/GUI behavior, **not** real projector calibration accuracy.
- Licensed vendor assets, original source and proprietary file formats are not used.

See README.md and docs/M8_CAMERA_CAPTURE.md for image capture and end-to-end demo. Use `python -m pytest tests/test_m10_corner_model.py tests/test_m10_corner_qt.py -q` for focused QA.
