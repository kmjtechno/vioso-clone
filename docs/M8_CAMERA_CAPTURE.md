# M8 — Opt-in Gray-code Camera / Projector Capture

The clone now contains an experimental camera acquisition path. It generates Gray-code patterns in the same order as the existing decoder, shows them on an explicitly selected projector display, records camera images and produces a capture manifest. It does **not** claim native VIOSO 7 compatibility or hardware acceptance.

## Requirements and safeguards

- A locally accessible OpenCV camera and a projector configured as an extended desktop.
- The operator must verify the projector's desktop origin. X=1920, Y=0 is an EXAMPLE, not an autodetected coordinate.
- Output must be a new, nonexistent directory. Existing captures cannot be overwritten.
- Physical projection requires the --confirm-display flag; Escape aborts.
- Errors may leave diagnostic PNGs but never a success manifest.
- Fullscreen OpenCV is an experimental projection mechanism; timing and hardware synchronization are not measured.

## Example (Windows PowerShell)

    python -m vclone gui

    python -m vclone capture-graycode --width 1280 --height 800 --camera 0 --projector-x 1920 --projector-y 0 --out "E:/KMJ/Captures/test-001" --settle-ms 500 --warmup-frames 3 --confirm-display

The capture directory will contain p00.png, n00.png, p01.png, n01.png, etc., plus capture_manifest.json. For 1280 x 800 there are 21 Gray-code pairs (42 images). Each stored PNG is a camera frame, not the projected reference image.

## Connect to the existing calibration engine

Create your own clone-format project.json pointing to the capture folder. The camera corners MUST be measured in the actual captured camera image; the following numeric coordinates are placeholders, not real measurements:

    {
      "name": "experimental-camera-project",
      "content_space": "flat",
      "displays": [{"id": 1}],
      "scan": {
        "dir": "E:/KMJ/Captures/test-001",
        "proj_size": [1280, 800],
        "content_size": [1920, 1080],
        "cam_corners": [[100,100],[900,100],[900,650],[100,650]],
        "content_corners": [[0,0],[1919,0],[1919,1079],[0,1079]],
        "nodes": [17, 9]
      }
    }

Then run from PowerShell, with paths adjusted:

    python -m vclone /L:E:/KMJ/Captures/test-001/project.json /Q:Calibrate
    python -m vclone /L:E:/KMJ/Captures/test-001/project.json /Q:Export
    python -m vclone preview E:/KMJ/Captures/test-001/project.json E:/KMJ/Captures/content.png E:/KMJ/Captures/preview.png

The existing calibration step reads the captured pNN and nNN files; the new synthetic tests exercise decoder parity.

## Evidence boundary

CI only tests synthetic camera callbacks, fake OpenCV camera/display interfaces, image sequencing, corruption guards, no-overwrite and CLI confirmation. It does not prove that a real P520 projector/camera pair achieves correct exposure, Gray-code decoding, calibration, warp or blending. Those require physical operator-controlled tests. Installed native VIOSO 7 software, proprietary binaries, and protected licensing logic are not accessed.
