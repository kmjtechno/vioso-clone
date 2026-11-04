# KMJ VIOSO-Clone v0.2.0a1 — Source/wheel alpha

This is a **Python source-and-wheel alpha** containing the independently implemented projector-calibration toolkit through M15. It is **not** a production-ready native VIOSO 7 clone, hardware-certified projector calibration system, or signed Windows EXE.

## Included features

- M1–M4: content/device configuration, synthetic camera geometry, Gray-code decoder, calibration algorithms, CPU warp preview, lightweight GUI and local project workflows.
- M5/M6: bounded **clone-specific** .sps container (NOT native VIOSO format).
- M7: bounded read-only SPS XML header metadata probe; no payload/native compatibility claim.
- M8: opt-in local camera capture and Gray-code pattern projection, guarded new output folder.
- M9: bounded opt-in calibrated projector still preview.
- M10: GUI image corner selection and capture setup; updates clone JSON projects and invalidates stale calibration.
- M11: fail-closed renderer on invalid inputs, alpha/mesh and extreme allocations.
- M12: installable Python wheel and vclone console script.
- M13: opt-in bounded local video CPU warp (single projector).
- M14: offline 2–8 projector calibrated image export and overlap weights, output integrity manifest.
- M15: opt-in verified multi-display still preview with per-projector desktop origin, without GPU synchronization.

## Verification policy

CI must test the **exact alpha release source commit** on Ubuntu and Windows, Python 3.13, run full regression, build a wheel, install it and execute `vclone --help` from outside checkout. Only a green CI run is a release receipt.

The wheel artifact is published from GitHub Actions for seven days; artifacts are *not* digitally signed or vendor-endorsed. Do not distribute to customers as stable software without separate security/hardware release gates.

## Blocked or not verified

- Actual P520 Windows camera, attached projectors and physical alignment QA.
- Representative owner-authorized original VIOSO 7 .sps sample import/export parity.
- Real-time synchronized multi-projector video/DirectX/NDI, color correction and optical edge-blend acceptance.
- Production UX and installation/uninstallation lifecycle, signing, stress/long-run reliability and supported-device matrix.
- Two hosted CI tests for locally installed original VIOSO7 reference INI resources are skipped because those resources are not present on CI runners.

**Zero vendor code, protected licensing logic, original application binaries or commercial keys are part of this alpha wheel.**
