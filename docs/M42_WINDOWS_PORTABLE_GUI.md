# M42 — Unsigned portable Windows GUI alpha

## What the archive contains

On a successful protected merge to `main`, GitHub Actions builds a
`KMJ-VIOSO-Clone-alpha-win64.zip` artifact. It contains an independently
implemented, **unsigned** `KMJ-VIOSO-Clone.exe` plus the bundled Python,
PySide6, OpenCV and NumPy runtime. It requires neither a separately installed
Python interpreter nor any vendor VIOSO program on the target Windows PC.

The ZIP is **not** a signed Windows installer, a commercial release or a
native VIOSO 7 replacement. Windows Defender/SmartScreen may apply normal
warnings to unsigned executables. Do not disable security policy, install
unsafe certificates or accept a publisher warning you cannot verify.

## Independent build/QA evidence

The M42 Windows workflow builds a PyInstaller `--onedir --windowed` package
and tests the full source regression before freezing. It invokes the actual
frozen `--self-test` executable, packages the onedir folder as a ZIP, expands
it into a new temporary directory, and re-runs the extracted executable's
`--self-test`. The self-test creates a Qt window **offscreen**, verifies
M38, M39 and M40 operator safety menu actions, then exits. It never opens
a camera, network stream, projector, operating-system display control, project
file or proprietary vendor binary.

The job reports the ZIP SHA-256 digest and explicitly labels real hardware,
native SPS interoperability and Authenticode signing **NOT VERIFIED**. Only
a `push` to `main` uploads a short-lived artifact (3-day retention). PR
builds smoke-test the code without accumulating a downloadable ZIP.

## Owner P520 usage — after independent verification

Once a successfully completed `main` workflow is available, an authorized
owner may retrieve its ZIP artifact via GitHub Actions, verify the artifact
digest printed in that same job's build log and extract it to a **new**
sibling folder; do not replace `E:\KMJ\Codex\VIOSO-Clone` or modify the
dirty `feat/sps-container-m5` checkout and REA notes. Launch the extracted
`KMJ-VIOSO-Clone.exe` without administrator privileges.

GitHub Actions does not install software on the P520. CI's `windows-latest`
host does not prove the P520's GUI, camera driver, projector display mapping,
USB permissions or the CP PLUS fisheye stream works. Real M40 camera
observation must be explicitly confirmed in-app; the two projectors can stay
**OFF** for all installation and camera-only checks.

## Acceptance limits

- Real webcam and CP PLUS fisheye stream opening: **NOT VERIFIED**
- CP PLUS camera intrinsics, undistortion and real Gray-code frame quality:
  **NOT VERIFIED**
- Real two-projector optical acceptance, seam blend, synchronization:
  **NOT VERIFIED**
- Proprietary VIOSO 7 `.sps` binary interoperability, vendor feature parity:
  **NOT VERIFIED**
- Signed installer and operating-system trust chain: **NOT PRESENT**

Track actual two-projector QA under
[Issue #67](https://github.com/kmjtechno/vioso-clone/issues/67).
No extra paid AI or third-party build provider is required; GitHub Actions
usage is still subject to the connected account's existing quota.
