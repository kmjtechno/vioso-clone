# RE notes: `.sps` and project XML (SPEC §3.6)

Clean-room notes, own words. Target: `SPCalibrator64.exe` 7.0.4.11052, SHA-256 `dab6ecf3da84cd43734afc6f5ae9856cb2ea7e9f0b68f11596f9a249a4a7d5c0`.
Method: static only, nothing executed. Licensing skipped. `SPeASY64.dll` not opened, and no sample `.sps` found.
Tags: **V-D** = verified (decompile). **V-A** = verified (assembly listing). **A** = anuman, basis stated.
Runtime reachability is not proven by any of these tags.

**Main result:** the exe's XML writer does not write `.sps`. It writes a separate project XML that stores a path to it. The `.sps` internals are **not established**.

## 1. Project XML writer: `0x14009e100`

- **V-D:** output path comes from the project struct at +0x54. If it is empty or document creation fails, the write is skipped.
- **V-D:** the XML declaration is version 1.0, utf-8. Root is `VIOSO`, with child `project` carrying `version` and `creator` (`SPCalibrator 7.0.4.11052`). The `version` value `1.0` was read from exe bytes; its use is V-D.
- **V-D:** helper `0x14009b390` emits each field as a generic `property` node, not as an element named after the field. Its items are `name`, `type`, optional `desc`, optional `default`.
- **V-D:** `type` is `int`, `float`, `uint`, `string`, `list` or `composite`, chosen from the value's VARIANT type. `list` and `composite` nodes skip range, default and value.
- **V-A:** the range is written only when upper > lower. Both writes use the name `min` and the lower value; no `max` is written, so the upper bound is not stored. **A:** the second write overwrites the first (DOM behaviour). Bug or intent: unknown.
- **A (vtable pattern):** items are attributes, and the value is node text.

| Field (V-D) | Source | Default | Meaning / values |
|---|---|---|---|
| `name` | struct start | none | project name |
| `type` | +0x48 | 1 | 0 legacy, 1 local, 2 local frustum, 3 multi, 4 multi frustum, 5 multi 3D |
| `state` | +0x4c | 0 | 0 undef, 1 new, 2 exported, 3 settled, -1 error |
| `method` | +0x50 | 1 | 1 single client / virtual displays, 2 multi client |
| **`spspath`** | +0x25c | `_Startup.sps` | full path to the "settings file" |
| `mrdpath` | +0x464 | `_Startup.mrd` | full path to model render definition file |
| `exoptdefpath` | +0x66c | `SPExtCalibCommOpDef.ini` | export definition file |
| `recalibscriptname` | +0x874 | `stdEdit.ini` | looks swapped with the next row; bug or intent unknown |
| `editscriptname` | +0x904 | `stdRecal.ini` | see above |
| `calibratescriptname` | +0x994 | `stdCal.ini` | calibration script name |
| `screen` | container | none | saved model creation parameters |
| `custommodel` | container | none | written only when screen type (+0xa24) is 8: `path`, `texture`, `scale` |
| `localDWC` | +0xf80 | none | written by a separate helper, `0x14009c4a0`; contents not analysed |

**`screen` children (V-D), as default [lower, upper] arguments; upper is not saved:**
- `type` 4 [0, 8]: 0 user defined, 1 Panadome, 2 Dome, 3 Cylinder, 4 Flat, 5 user defined. The code's upper bound and `custommodel` check use 8, which the comment does not list.
- `outside` 0 [0, 1]: 1 flips the model faces.
- `radius` 1000, `width` 3200, `height` 2000, `horizontalstep` 100, `verticalstep` 100: all [1, 1e7], mm.
- `longitudestep` 2, `latitudestep` 2: both [0.1, 10].
- `leftangle` -90 and `bottomangle` -45: both [-179, 0].
- `topangle` 45, `rightangle` 90, `latitudestartangle` 0, `latitudeendangle` 90: all [0, 179].

Offsets for these are in the writer at +0xa24 to +0xb68. Called from `0x140029cc0`, `0x14002c630`, `0x14002c6a0` (V-D). After `localDWC`, `0x1400a1a40` adds something not analysed.

## 2. Save operation: `0x140183600`

- **V-D:** inputs are window, path, show-message flag and flags. An empty path returns -1. `.sps` is appended if the last 4 characters do not match.
- **V-D:** builds a 0x1a0-byte request: +0 = 0xb, +4 = 0x11, +8 = -1, +0x10 = 0, +0x1c = (flags & 0x1f20) | 0x208f, +0x44 = path, +0x148 = 1, +0x194 = -1. It then calls `SPBehaviourRequest`; return 1 is success.
- **V-D:** on success it stores the path and shows a saved or startup-settings message, depending on bit 0x100. **A (message text):** bit 0x100 means "save as startup settings".
- **V-D:** file pickers set state 5 or 7 with step 4 (`0x14018a0f0`, `0x14018a450`), and the Nvidia prompt `0x140190a90` sets state 0x11, then each posts message 0x441. Handler `0x14017a960` calls the save op; state 6 gets flag 0x100, but who posts state 6 is unknown.
- **A (byte scan of message map, behaviour matches):** message 0x441 is routed to `0x14017a960`.
- **A (symmetry):** the serializer is in `SPeASY64.dll`; the exe only passes a request.

Load counterpart: `0x140182e80` (V-D) uses the same layout with +0 = 0xa and +0x10 = 1, per path, via `SPBehaviourRequest`. **A (role, callers' `.sps` filter):** code 0xa means load `.sps`.

## 3. Embedded task-script XML

- **A (exe bytes and reference map, not decompile):** six XML scripts at file offsets 0x70d0b0, 0x70f490, 0x70fb20, 0x711280, 0x7154f0, 0x716c80 are automation task templates, **not** `.sps` samples or a schema. Their user appears to be `0x140029cc0`.
- **A (same basis):** they contain a save task of type File, subtype sps, placed after calibration and before presentation reconfig. No load task was found (bounded search).
- **A (weak):** their `C1.DevSel` parameter names may influence what the calibration stores. They do not prove any `.sps` field.

## 4. Verified vs anuman summary

**Verified:**
- V-D: writer structure and fields (§1), save op (§2), load op request, and the handler's state split: 2/3 = load, 5/6/7/0x11 = save.
- V-D: `spspath` calls `.sps` a "settings file". SPEC's "Project file" wording may need correcting (**A**).
- V-A: the `min`-only range behaviour.

**Anuman:**
- `.sps` is XML, or optionally compressed: only `xmlfile`, `bSaveCompressed`, `compressLevel`, `SPSetDefaultXmlFileSaveParam_*` strings and imports support this, no decompile of the format.
- LZO as the compressor: only a URL string and an import. pugixml use for `.sps`: only a source path string.
- `LastSPSDir` appears to hold a full path (V-D usage in `0x140190a90`; the persistence helpers are A).
- CLI parser: not located; `/L:`, `/S:`, `/O:` not found as literals (bounded).

**Unknown:** `.sps` fields, encoding, compression, version value. Next evidence needed: `SPeASY64.dll` analysis or a real sample capture.
