# M15 — Experimental multi-display still presentation

The independent clone can display an **M14 offline multi-projector export** on multiple fullscreen OpenCV windows, using one explicitly selected desktop origin for each projector. The export's PNG hashes, manifest schema, file order and image sizes are checked *before* any physical projector window opens.

This feature provides bounded multi-display **still** presentation only. It does not prove synchronized video output, genlock, DirectX/GPU swap-chains, hardware-calibrated edge blending, or native VIOSO 7 parity.

## Use

First generate 2–8 offline projector PNGs and the manifest:

    vclone export-multi shared-content.png fresh-output projector-1.json projector-2.json --gamma 2.2

Find each physical projector's real top-left coordinate in Windows extended-desktop settings. The following origins are **examples only**:

    vclone present-multi fresh-output --origin 1920,0 --origin 3840,0 --duration-ms 5000 --confirm-display

Every projector needs a **distinct** origin. Use `--origin` once for each PNG in manifest order. The command refuses invalid origins, duplicate destinations, tampered PNG/manifest data, symlinked paths and missing confirmation. Display duration is 1..30,000 ms; ESC may end the preview. All opened windows close even after a display error.

The result prints `hardware_acceptance=NOT_VERIFIED`. A successful CI test proves that the windows were invoked in the expected sequence using mocks; it does not prove the physical monitors or projectors are correctly configured.

## Security / limits

- 2–8 projector files, each max 1920×1080 and 32 MiB PNG bytes.
- Manifest max 64 KiB, schema exact match, filenames forced to `projector_NN.png`, SHA-256 verified.
- No network URLs, project file parsing, native VIOSO assets, audio, video streams, licensing controls or file writes in this display command.
- The display origin is operator-provided; no automatic projector discovery or refresh synchronization. Use an actual P520 display acceptance session to verify physical coordinates, geometric correction, gamma and edge-blend seam quality.
