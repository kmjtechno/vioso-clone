# M38 — Read-only two-projector seam check in the GUI

The clone's **Calibration > Compare two-projector seam (offline)...** action
makes the M37 geometry preflight accessible from the PySide6 application.

1. Open the **first already calibrated** clone JSON project with **File > Open**.
   Unsaved in-memory calibration changes remain in memory and are never
   overwritten by the check.
2. Select **Calibration > Compare two-projector seam (offline)...**.
3. Choose a **different already calibrated** clone JSON project for the second
   projector. The dialog displays overlap of the smaller projector footprint,
   union content coverage, uncovered content and an explicit software gate.
4. A software PASS is shown as an informational dialog. Blocked geometry
   remains a warning, even if the input JSON files were readable.

**Safety:** Neither action opens camera streams, changes Windows display
configuration, projects Gray-code, calls proprietary VIOSO code, alters
the currently loaded project, nor writes to either JSON file. Opening the second
project uses the existing clone non-symlink and size-guarded loader. Same-file
selection and malformed data fail closed. The session log records only the
software gate, never camera URLs or credentials.

**Limits:** PASS_SOFTWARE_GEOMETRY_ONLY is not physical optical acceptance,
projector identity mapping, synchronization, native SPS compatibility or
commercial VIOSO 7 parity. The owner must separately confirm the two projector
identities, power them ON when prompted for actual optical capture, and run
sequential projector calibration. Until then both may remain OFF.

This GUI step has no additional paid dependency. M38 introduces no auto
activation or capture behavior.
