# VIOSO-Clone (vclone)

An independently implemented Python/OpenCV projector-calibration application under active development. The goal is functional VIOSO-like projection calibration without copying vendor code, assets, licensing, or protected formats.

This repository is source code, not a finished replacement for VIOSO 7. Synthetic calibration and software-rendered previews are tested. Native .sps interoperability, real-time multi-projector output and physical hardware acceptance remain **NOT VERIFIED**.

## Current features

| Module | Current status |
| --- | --- |
| Gray-code generation/decoding and projector-to-camera mapping | Implemented; synthetic tests |
| Camera intrinsics and quality gates | Implemented with OpenCV |
| Homography, multipane RANSAC and warp mesh | Implemented; synthetic tests |
| Edge blending and CPU frame warp preview | Implemented; no dedicated GPU swap-chain |
| Project JSON, design/calibration/edit/export CLI | Implemented |
| Clone-specific .sps container (M5/M6) | Implemented with bounded parser; **NOT native VIOSO compatible** |
| Read-only .sps XML metadata inspector (M7) | Implemented; explicitly no payload/native compatibility claim |
| Experimental projector Gray-code / camera capture (M8) | Implemented, opt-in; **physical hardware not yet verified** |
| Experimental calibrated still-frame projector output (M9) | Opt-in bounded OpenCV fullscreen; **not hardware/sync verified** |
| Minimal PySide6 GUI | Implemented; not full commercial UI |
| Camera calibration corner editor (M10) | Setup capture folder and select four image corners; physical accuracy unverified |
| Player, remote and automation script modules | Implemented at software level; no real NDI/real-time output |
| Local calibrated video playback (M13) | Bounded single-projector CPU warp; no synchronized GPU/NDI/hardware acceptance |
| Offline multi-projector blend/export (M14) | 2–8 calibrated PNG outputs with overlap weighting; no synchronized display |
| Verified multi-display still presentation (M15) | Opt-in fullscreen windows for M14 PNGs; no hardware synchronization |
| Original VIOSO 7 formats, proprietary render API, hardware parity | **Not implemented / not verified** |

## Install as a Python package (M12)

A versioned Python wheel and `vclone` console entrypoint are provided. Current development alpha is **v0.2.0a1**; see [alpha release notes](docs/RELEASE_0_2_0_ALPHA.md). Use a clean Python virtual environment:

    python -m pip install ".[gui]"
    vclone --help
    vclone gui

To create a redistributable wheel from the checked-out source:

    python -m pip install build
    python -m build --wheel

The wheel installs `vclone` and its independent Python code. This is **not a signed Windows .exe, commercial installer, calibrated hardware release, or native VIOSO file compatibility**. Hardware operations always require local user authorization and their explicit confirmation flags.

## Clone project settings XML (M20)

This is a **clone-specific** settings format and is **NOT** a native VIOSO 7 .sps format.

    vclone settings-new room-settings.xml --name "Room A"
    vclone settings-check room-settings.xml

The create command uses exclusive creation and never overwrites an existing file.
The check command only reads regular non-symlink files, checks an input size limit
and rejects malformed XML, DTDs, unknown fields and unexpected attributes.
Neither command uses a camera, projector, vendor licensing or original VIOSO files.

## Quick start

Use a Python environment with OpenCV and NumPy. PySide6 is optional for the GUI; install the GUI-capable OpenCV build for an actual projector window.

    python -m pip install numpy opencv-python pytest PySide6
    python -m pytest -q
    python examples/synthetic_demo.py
    python -m vclone gui

The synthetic demo writes pNN/nNN camera images, a clone-format JSON project, warp.json, content.png and preview.png into a newly created temporary folder. It never uses a real camera or projector. The demo refuses an output folder containing existing files.

## Read-only capture quality preflight (M25)

After capturing Gray-code camera images and before calibration, run
`vclone capture-check <capture-folder>`. It checks manifest/pattern integrity,
pairwise contrast, decoded pixel coverage and projector-axis span without
opening a camera/projector or writing files. See
[the M25 capture quality guide](docs/M25_CAPTURE_QUALITY.md).
This is software screening only, not optical calibration certification or
native VIOSO 7 compatibility.

## Experimental real camera acquisition

Only use with an explicitly identified external projector display and camera:

    python -m vclone capture-graycode --width 1280 --height 800 --camera 0 --projector-x 1920 --projector-y 0 --out "E:/KMJ/Captures/run-001" --confirm-display

The destination must not exist. The displayed coordinates are examples and must be confirmed by the operator; the camera window will not open without the confirmation flag. Camera timing/contrast and projector suitability need real tests. See docs/M8_CAMERA_CAPTURE.md for the manual project configuration and calibration pipeline.

## Show a calibrated still on a projector

A clone JSON project with valid calibration can render a corrected still frame on an explicitly selected extended-desktop projector output. Confirm display coordinates and use a bounded duration:

    python -m vclone present-preview project.json content.png --projector-x 1920 --projector-y 0 --duration-ms 5000 --confirm-display

This uses OpenCV fullscreen for a single still frame, not a synchronized video renderer or DirectX backend. The sample X=1920/Y=0 coordinates are **not autodetected**. See docs/M9_PROJECTOR_STILL_OUTPUT.md.

## Capture actual Gray-code patterns from the GUI (M21)

Use Calibration > Capture Gray-code from camera in the PySide6 GUI. Choose a NEW
capture folder, projector resolution, content size, camera index and actual
extended-display X/Y coordinates. The OK action stays disabled until the local
operator confirms the display choice. ESC aborts acquisition. If a capture
fails, no completed manifest is reported and the existing project settings are
not changed. After a successful capture, the session connects the new folder,
then use Calibration > Select camera corners and run Calibrate.

The GUI capture path is still experimental: physical hardware alignment,
latency and optical acceptance must be tested on the actual P520/projector.
No original VIOSO code or native settings file is used.

## Select camera corners in the GUI

Run `python -m vclone gui`, choose **Calibration → Setup capture folder and dimensions**, then **Calibration → Select camera corners**. Click the four corners in the p00.png camera image in TL → TR → BR → BL order. The editor validates convex geometry, sets matching content corners and invalidates stale calibration. Save the clone-format project through File → Save As before running Calibrate. See docs/M10_CAMERA_CORNER_EDITOR.md. The GUI does not automatically certify real hardware alignment.

## CPU calibration preview in GUI (M22)

After a clone project has a calibrated mesh, choose **Calibration > Preview calibrated
content (CPU)**, select a local image, and inspect the corrected projector frame
inside the application. Optionally choose **Save CPU preview as new PNG**; the
export refuses existing files and does not modify the project or use a projector.
The preview is a software-only simulation and never certifies physical alignment.

## Experimental calibrated local video playback

With a valid calibrated clone project, and after confirming the projector display's actual desktop position:

    vclone present-video project.json local-video.mp4 --projector-x 1920 --projector-y 0 --fps 24 --seconds 10 --confirm-display

The playback is CPU-warped, bounded to 30 seconds and at most 30 requested FPS. It is **not refresh-synchronized GPU video output**, and it does not include native VIOSO7 decoding, multi-projector genlock or NDI. See docs/M13_VIDEO_PLAYBACK.md.

## Opt-in color balance for offline multi-projector previews (M27)

For 2–8 separate calibrated clone-format projectors, `export-multi` can apply
per-projector bounded BGR gain and black subtraction from a strict JSON profile:

    vclone export-multi content.png ./new-output p1.json p2.json --color-balance balance.json

See [M27 color-balance preview](docs/M27_COLOR_BALANCE_PREVIEW.md) for the
profile schema and verification limits. It does **not** measure actual projector
black levels, gamma or colorimetry and does not claim hardware calibration.

## Offline multi-projector blend previews

For 2–8 independently calibrated clone projects sharing one content resolution:

    vclone export-multi shared-content.png new-output-dir projector-1.json projector-2.json --gamma 2.2

This writes a separate calibrated PNG for each projector and a hash-verified manifest in a **new** output directory, with content-space overlap blending. This is not simultaneous physical projector playback. See docs/M14_MULTI_PROJECTOR_OFFLINE.md.

## Show verified multi-projector still previews

After `export-multi` creates 2–8 PNG files and a checksum manifest, display them on distinct confirmed extended-desktop projectors:

    vclone present-multi new-output-dir --origin 1920,0 --origin 3840,0 --duration-ms 5000 --confirm-display

Each `--origin` is an example; operators must supply the actual display origin for each projector. The files are checked against manifest SHA-256 before windows are opened. This is **not** genlocked or synchronized video; see docs/M15_MULTI_DISPLAY_STILL.md.

## Calibration CLI

Use the clone's own project.json with measured corner points and scan folder:

    python -m vclone /L:project.json /Q:Calibrate
    python -m vclone /L:project.json /Q:Export
    python -m vclone preview project.json content.png preview.png

Do not treat a successful preview as hardware calibration proof. Design, editing, remote and player features have narrower verified scope than a full proprietary software product.

## Project structure

- vclone/calib.py, intrinsics.py, render.py: calibration algorithms and CPU software output
- vclone/project.py, cmdline.py, gui.py, gui_model.py: project workflow, command line and minimal GUI
- vclone/sps.py and sps_probe.py: clone SPS and read-only bounded metadata inspection
- vclone/capture.py: opt-in camera/projector acquisition
- vclone/output.py: opt-in bounded still-frame projector output
- vclone/video_output.py: bounded opt-in local video decoding and CPU-warped fullscreen output
- vclone/multi_output.py: offline multi-projector warp and normalized content-space overlap export
- vclone/multi_present.py: verified bounded multi-display still presentation
- vclone/script.py, remote.py, player.py: software workflow components
- examples/synthetic_demo.py: runnable end-to-end synthetic calibration
- tests/: Python regression suites; hosted Windows/Linux CI tests synthetic workflows, not physical hardware
- SPEC.md and docs/: clean-room specification, limitations and evidence

No source from SPCalibrator64.exe, SPeASY64.dll, license/protector DLLs or third-party protected software is included.
