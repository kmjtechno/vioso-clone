# SPCalibrator64 clone — clean-room feature & format spec (draft 0)

Source of facts: static survey of `C:\Program Files\VIOSO7\SPCalibrator64.exe`
(PE32+ amd64, MFC GUI, sha256 dab6ecf3…7d5c0), its install dir, shipped `.ini`
files and shipped manuals. No code, assets or licence logic are copied.
**Out of scope by design:** Soraco QLM / LicProtector / `.lic` handling.
The clone has its own (no-op / open) licensing.

## 1. Architecture of the original
- `SPCalibrator64.exe` = thin MFC GUI. Real logic = `SPeASY64.dll` (SPRunTimeEnvironement API).
- Rendering: OpenGL (GLEW) + D3D9; images: FreeImage, GDI+; vision: OpenCV 2.2 (via `VIOSO_OpenCVImpl64.dll`); 3D import: Assimp; HID: hidapi; streaming: NDI.
- Companions: ProjectDesignerUI (WPF), PointPicker, Blackbox64/VRGB, CalibImgFileViewer, spsDispAlloc.

## 2. Functional modules to reproduce (priority order)
| # | Module | Notes |
|---|--------|-------|
| 1 | Project manager | steps: Design, Calibrate, Edit, Edit MRD, Export, Recalibrate, Activate, Deactivate, Configure, RecoverExport; JSON `ProjectConfig.json` preconfig |
| 2 | Device DB | `SPDevices.ini` camera intrinsics (see §3.1) + import of external intrinsics |
| 3 | Camera intrinsics calc | `SPCalculateCameraIntrinsics` equivalent (OpenCV calibrateCamera) |
| 4 | Display topology | `SPSurDef.ini` (§3.2), `SPManualMPPreset.ini` manual multi-projector presets |
| 5 | Content spaces | `SPContentSpaces.ini` (§3.3): plane, sphere/dome, custom 3D models, perspective-view pose params |
| 6 | Calibration engine | structured-light scan → camera↔projector map → warp mesh + edge-blend spline + black level; multi-calibration ROI; Recalib2D |
| 7 | Export | MRD / VC / VWF-style warp+blend outputs, compressed XML save (level 3) |
| 8 | Command line | §4 |
| 9 | Script engine | XML `<task action=…>` (Script_Reference.pdf, 25 actions) |
| 10 | Remote control | TCP/UDP/HTTP `player.htm?…`, `control.htm?…`, `presenter.htm?…` (Remote_Control_Reference.pdf) |
| 11 | Player / playlist | media playback of calibrated output, NDI in/out |
| 12 | 3D tools | simple 3D model creation/export, VRED pose load |

## 3. File formats (observed)
### 3.1 SPDevices.ini
`<VIOSO><SPeASY><File version="1.0.0"/><InputDevices><Camera Name=".."><IntrinsicParameter><Resolution width height><FocalLength X Y/><PrincipalPoint X Y/><RadialDistorsion K1 K2 K3/><TangentialDistorsion P1 P2/></Resolution>…`
### 3.2 SPSurDef.ini
`<DesktopDisplay name core posX posY sizeX sizeY rows cols rotation><Part iRow iCol name/>` and
`<logicalDisplay name idString tProtocol><topology rows cols/><display iRow iCol idString core/>`.
### 3.3 SPContentSpaces.ini
`<ContentSpace Name><Common width height typ/><DefaultModel l t r b/>` or `<Model3D Name tForceCullMode fCreateMesh><PosScale/><BasePoint/><SubMesh Name index/></Model3D><ModelPoseParameter3D><Resolution width height typ bFixLookAt bReadable><EyePoint/><ViewDir/><DevX/><DevY/><ViewSize/><Center/><CalcParam bAvailable/>`.
### 3.4 SPManualMPPreset.ini
`<MPPreset><Common tArrangement/><CalibSpace l t r b/><VirtualCanvas l t r b/><Display name core l t r b tUse="normal|Keystone Rect"/>`.
### 3.5 SPeASY.ini / Calibrator.ini
XML (`DebugOptions: ErrorHandling LogFileLevel, CatchUnhandled, SaveErrorDump, AutoRestart…, DefaultSavePath, Image PermitSaving, Camera bShowStreamDuringCalib, Calibration bLoadOnError`) and classic INI (`[common] GUIProfile, [output] tDx9_Presentation, [xmlfile] bSaveCompressed/compressLevel, [calibration] tCalibMethod`).
### 3.6 Project file `.sps` (XML, optionally compressed) — structure still to be inferred from a sample project (none shipped; need user-provided sample or runtime capture).

## 4. Command line (from CmdLn_Param.pdf)
`/0 /1 /a /A /D:n /E /F:"profile" /I:"ip" /J:n /H[:"file"] /L:"sps" /Lang:n /M /O:"path" /P:"path" /Q:"step[;CloseAfter=yes]" /R /S:"path" /V /X:"name" /Z`

## 5. Open items / honest limits
- Calibration math and `.sps` binary details are not in the manuals; they need runtime captures (REA `observe_native_calls` / Frida) or clean-room design. Hardware acceptance cannot be certified by unit tests.
- "Full" parity (18 MB, ~10 libs, 20 years of features) is multi-month work; this spec defines milestones M1–M4 below.

## 6. Milestones
- **M1** Core library + CLI: ini/XML parsers (§3), device DB, intrinsics calc, project model, `/Q` steps stubs. Tests against shipped inis.
- **M2** Calibration engine: Gray-code/line scan decode, homography+mesh warp, edge-blend; synthetic-camera tests.
- **M3** GUI (Qt or WPF) mirroring menus/dialogs from PE resources; DX/GL output.
- **M4** Script engine + remote control server + player/playlist.
