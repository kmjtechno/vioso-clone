# M9 — Calibrated still-frame projector presentation

The existing CPU projector warp can now produce an in-memory frame and optionally show it using a bounded fullscreen OpenCV window. This is a **still-image experimental output**, not a video player, a synchronized GPU swap-chain, a native VIOSO projector driver, or physical-calibration acceptance.

## How to run

Create a calibrated clone-format JSON project by running the existing calibration workflow. The project needs a valid result.mesh and scan.proj_size. Provide a content image and select the projector's real top-left position in the extended desktop.

    python -m vclone present-preview project.json content.png --projector-x 1920 --projector-y 0 --duration-ms 5000 --confirm-display

The coordinates above are **examples**. Verify the actual projector monitor before running. The default display time is five seconds; the allowed duration is 1..30,000 milliseconds. Without --confirm-display the command refuses without opening any display window. The OpenCV window is closed even if a presentation step fails.

If you only want a PNG, continue using the existing headless path:

    python -m vclone preview project.json content.png preview.png

The new in-memory render function produces the same pixel data as the existing PNG preview before encoding. Automated tests validate this identity and exercise a fake OpenCV display, including rejection of invalid frames, coordinate/time limits and cleanup after simulated failures.

## Limitations

- It is a single calibrated still image, not continuous 60-Hz synchronized playback or hard real-time output.
- Monitor selection is operator-provided; no automatic projector discovery.
- Gamma, black level, hardware-specific color matching, geometric correction and physical projector calibration are not verified.
- The current frame is generated from the clone's independently authored mesh, not a native VIOSO7 proprietary file.
- Passing CI with fake displays and offscreen Qt is **not** real projector QA.
