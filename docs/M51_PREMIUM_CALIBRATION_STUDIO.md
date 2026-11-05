# M51 — Premium Calibration Studio UI (functional PySide6)

The early Windows alpha used default light native Qt controls with one long
row of step buttons, a large blank activity area, a CPU preview label and a
Calibration menu. It was functional scaffolding rather than a finished user
interface. The owner's Windows screenshots confirmed that this layout is not
appropriate for a professional dual-projector calibration tool.

M51 implements a dark, independent Calibration Studio interface in the
real `vclone.gui.MainWindow` source, **not an illustrative screenshot**:

- Deep navy/graphite background with teal primary action, visible typography,
  calibrated spacing, high contrast and distinct left workflow navigation.
- Dedicated header and three real status cards: Camera, Projector rig and
  Optical calibration. All begin at **NOT TESTED / NOT MAPPED /
  NOT VERIFIED**. Observing six camera frames is never labeled successful
  optical geometry.
- The complete existing `Session.steps()` functionality remains represented
  in a scrollable sidebar. Unsupported functions remain disabled.
- Four top-level controls connect to the same real methods:
  `Connect ONVIF Camera`, `Check Displays`, `Capture Gray-code`,
  `Preview Content`. The existing File and Calibration menu structure and
  names are preserved for established workflows and accessibility.
- Large, framed calibration viewport with a real CPU content preview,
  non-exportable before valid preview exists.
- Console-like session activity panel and non-misleading hardware safety
  guidance.
- Minimum 1000×660 workspace; resizable up to a larger studio desktop.
- No automatic camera open, ONVIF scan, projector startup, filesystem
  write, signing step or license bypass occurs when the window opens.

The shell is deliberately Qt/widgets and theme CSS, so PyInstaller
bundles it with the existing Windows alpha and original Session backend.
M51 does **not** rewrite project serializers, calibration algorithms,
camera connection behavior or the hardware consent gates.

## Release verification

- Offscreen Qt construction and menu/step parity tests.
- Real button-to-method signal wiring tests using synthetic replacement
  methods (no device access).
- Explicit status assertion refusing camera/projector optical PASS claims.
- Frozen Windows EXE + extracted ZIP `--self-test` must pass.
- GitHub workflow must execute all steps on the exact M51 head and PASS
  before this design can be merged or released.

If GitHub hosted CI returns zero-step failure (runner allocation/plan
restriction), do not claim source tests PASS or publish M51 as a release;
keep the PR open until a real trusted runner executes tests.

## Still unverified hardware acceptance

P520 source folder `E:\KMJ\Codex\VIOSO-Clone\FullSource` has been
verified empty; connected CodeBridge currently lists only
`python_verify:test` and `rea_doctor:check`. No P520 Git full-clone,
new source GUI installation, ONVIF live frame probe, native fisheye 1O
optics, both projector geometry/edge blending or vendor VIOSO 7 SPS
interoperability can be inferred from hosted offscreen GUI tests.

The professional UI must therefore visibly preserve **ALPHA / NOT VERIFIED**
status until hardware evidence is actually collected by the owner.
