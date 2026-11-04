import argparse
import sys
from pathlib import Path

from . import cmdline, configs, project

DEPLOY = Path(r"C:\Program Files\VIOSO7\Deploy")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0].startswith("/"):
        cl = cmdline.parse(argv)
        print(cl)
        return project.run_cmdline(cl)
    ap = argparse.ArgumentParser(prog="vclone")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("devices", help="list camera intrinsics DB")
    d.add_argument("--file", default=str(DEPLOY / "SPDevices.ini"))
    c = sub.add_parser("spaces", help="list content spaces")
    c.add_argument("--file", default=str(DEPLOY / "SPContentSpaces.ini"))
    v = sub.add_parser("preview", help="software-render calibrated content to a NEW PNG; refuses overwrite")
    v.add_argument("project")
    v.add_argument("content")
    v.add_argument("out")
    cam = sub.add_parser("capture-graycode", help="opt-in camera acquisition of projector Gray-code patterns")
    cam.add_argument("--width", type=int, required=True, help="projector width (2..1920)")
    cam.add_argument("--height", type=int, required=True, help="projector height (2..1080)")
    cam.add_argument("--out", required=True, help="new directory; existing folders are never overwritten")
    cam.add_argument("--camera", type=int, default=0, help="local OpenCV camera index")
    cam.add_argument("--projector-x", type=int, required=True, help="projector display's screen X")
    cam.add_argument("--projector-y", type=int, required=True, help="projector display's screen Y")
    cam.add_argument("--settle-ms", type=int, default=250, help="settling time per projected frame")
    cam.add_argument("--warmup-frames", type=int, default=2, help="discarded camera frames per pattern")
    cam.add_argument("--confirm-display", action="store_true", help="I verified the projector display coordinates")
    cq = sub.add_parser("capture-check", help="read-only Gray-code capture image integrity and decoding quality")
    cq.add_argument("directory", help="existing clone Gray-code capture folder")
    cq.add_argument("--margin", type=int, default=20, help="minimum absolute p/n contrast (0..254)")
    cq.add_argument("--min-valid-fraction", type=float, default=0.30, help="decoded valid camera fraction (0.01..1)")
    cq.add_argument("--min-axis-span", type=float, default=0.25, help="minimum decoded projector x/y span (0.01..1)")
    sub.add_parser("gui", help="launch the optional PySide6 project editor")
    still = sub.add_parser("present-preview", help="opt-in bounded calibrated still on a projector")
    still.add_argument("project", help="calibrated clone-format JSON project")
    still.add_argument("content", help="source image to warp")
    still.add_argument("--projector-x", type=int, required=True)
    still.add_argument("--projector-y", type=int, required=True)
    still.add_argument("--duration-ms", type=int, default=5000, help="1..30000 ms")
    still.add_argument("--confirm-display", action="store_true")
    video = sub.add_parser("present-video", help="experimental bounded local video through calibrated CPU mesh")
    video.add_argument("project", help="calibrated clone JSON project")
    video.add_argument("video", help="local MP4/MOV/AVI/MKV/WEBM file")
    video.add_argument("--projector-x", type=int, required=True)
    video.add_argument("--projector-y", type=int, required=True)
    video.add_argument("--fps", type=float, default=24.0, help="bounded playback pacing 1..30")
    video.add_argument("--seconds", type=float, default=10.0, help="bounded duration 0..30")
    video.add_argument("--confirm-display", action="store_true", help="operator confirms destination projector")
    multi = sub.add_parser("export-multi", help="offline warp/blend PNG outputs for 2-8 calibrated projectors")
    multi.add_argument("content", help="shared content image")
    multi.add_argument("output_dir", help="new output folder, never overwrite")
    multi.add_argument("projects", nargs="+", help="2..8 calibrated clone JSON project files")
    multi.add_argument("--gamma", type=float, default=2.2, help="blend gamma 0.5..4.0")
    md = sub.add_parser("present-multi", help="show verified M14 PNGs on 2-8 selected desktops")
    md.add_argument("directory", help="M14 offline export directory")
    md.add_argument("--origin", action="append", required=True, help="x,y desktop coordinate (repeat per projector)")
    md.add_argument("--duration-ms", type=int, default=5000)
    md.add_argument("--confirm-display", action="store_true")
    nset = sub.add_parser("settings-new", help="create a NEW clone-only settings XML, not a native .sps")
    nset.add_argument("out", help="new output path, existing paths never overwritten")
    nset.add_argument("--name", default="untitled")
    cset = sub.add_parser("settings-check", help="read-only validation of a clone-only settings XML")
    cset.add_argument("file")
    a = ap.parse_args(argv)
    if a.cmd in ("settings-new", "settings-check"):
        from . import projectxml
        try:
            if a.cmd == "settings-new":
                if not 0 < len(a.name) <= 256 or any(ord(c) < 32 for c in a.name):
                    raise ValueError("name must be 1..256 printable characters")
                dest = Path(a.out)
                payload = projectxml.to_xml(projectxml.ProjectSettings(name=a.name)) + "\n"
                with dest.open("x", encoding="utf-8", newline="\n") as out:
                    out.write(payload)
                print("clone_settings=CREATED; native_vioso_sps_compatible=NO")
            else:
                inp = Path(a.file)
                if inp.is_symlink() or not inp.is_file():
                    raise ValueError("settings XML must be a regular non-symlink file")
                if inp.stat().st_size > projectxml.MAX_XML_BYTES:
                    raise ValueError("project XML exceeds 1 MiB input limit")
                settings = projectxml.from_xml(inp.read_text(encoding="utf-8"))
                print(f"clone_settings=VALID; screen_type={settings.screen.type}; native_vioso_sps_compatible=NO")
        except (ValueError, OSError) as err:
            print(f"clone settings refused: {err}", file=sys.stderr)
            return 2
        return 0
    if a.cmd == "present-multi":
        if not a.confirm_display:
            print("multi-display refused: --confirm-display required", file=sys.stderr)
            return 2
        from . import multi_present
        try:
            origins = []
            for point in a.origin:
                parts = point.split(",")
                if len(parts) != 2:
                    raise multi_present.MultiDisplayError("origins must be x,y coordinates")
                origins.append((int(parts[0]), int(parts[1])))
            receipt = multi_present.present_multi(
                a.directory, origins, duration_ms=a.duration_ms, confirmed=True)
        except (multi_present.MultiDisplayError, multi_present.cv2.error,
                ValueError, TypeError, OSError) as e:
            print(f"multi-display refused: {e}", file=sys.stderr)
            return 2
        print(f"displayed {receipt.displays_presented} previews; "
              f"hardware_acceptance={receipt.hardware_acceptance}")
        return 0
    if a.cmd == "export-multi":
        from . import multi_output
        try:
            if not 2 <= len(a.projects) <= 8:
                raise multi_output.MultiExportError("provide 2..8 project JSON files")
            projects = [project.Project.load(p) for p in a.projects]
            result = multi_output.export_multi(
                projects, a.content, a.output_dir, gamma=a.gamma)
        except (multi_output.MultiExportError, multi_output.cv2.error,
                OSError, ValueError, TypeError, KeyError) as e:
            print(f"multi-projector export refused: {e}", file=sys.stderr)
            return 2
        print(f"exported {len(result['projectors'])} projector previews to {a.output_dir}")
        print("hardware_acceptance=NOT_VERIFIED")
        return 0
    if a.cmd == "present-video":
        if not a.confirm_display:
            print("video refused: --confirm-display required", file=sys.stderr)
            return 2
        from . import video_output
        try:
            receipt = video_output.play_file(
                project.Project.load(a.project), a.video,
                projector_x=a.projector_x, projector_y=a.projector_y,
                fps=a.fps, seconds=a.seconds, confirmed=True)
        except (project.MissingInput, video_output.VideoPlaybackError, video_output.cv2.error,
                OSError, ValueError, TypeError) as e:
            print(f"video refused: {e}", file=sys.stderr)
            return 2
        print(f"video preview completed: {receipt.frames_presented} frames, "
              f"escape={receipt.stopped_by_escape}, "
              f"hardware_acceptance={receipt.hardware_acceptance}")
        return 0
    if a.cmd == "present-preview":
        if not a.confirm_display:
            print("presentation refused: --confirm-display required", file=sys.stderr)
            return 2
        from . import output
        try:
            frame = project.render_frame(project.Project.load(a.project), a.content)
            output.present_still(frame, projector_x=a.projector_x,
                                 projector_y=a.projector_y, duration_ms=a.duration_ms,
                                 confirmed=True)
        except (project.MissingInput, output.PresentationError, output.cv2.error,
                OSError, ValueError, TypeError) as e:
            print(f"presentation refused: {e}", file=sys.stderr)
            return 2
        return 0
    if a.cmd == "capture-check":
        import json
        from .capture_check import CaptureCheckError, check_capture
        try:
            report = check_capture(a.directory, margin=a.margin,
                                   min_valid_fraction=a.min_valid_fraction,
                                   min_axis_span=a.min_axis_span)
        except (CaptureCheckError, ValueError, TypeError, OSError) as exc:
            print(f"capture quality refused: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(report, sort_keys=True))
        return 0
    if a.cmd == "capture-graycode":
        from . import capture
        try:
            receipt = capture.capture_opencv(
                a.width, a.height, a.out, camera_index=a.camera,
                projector_x=a.projector_x, projector_y=a.projector_y,
                settle_ms=a.settle_ms, warmup_frames=a.warmup_frames,
                confirmed=a.confirm_display)
        except (capture.CaptureError, capture.cv2.error, OSError, ValueError) as e:
            print(f"capture refused: {e}", file=sys.stderr)
            return 2
        print(f"saved {len(receipt.image_files)} image files to {a.out}")
        print(f"manifest: {Path(a.out) / 'capture_manifest.json'}")
        return 0
    if a.cmd == "gui":
        try:
            from .gui import main as gui_main
        except ImportError as e:
            print(f"GUI requires PySide6: {e}", file=sys.stderr)
            return 2
        return gui_main([])
    if a.cmd == "preview":
        try:
            project.render_preview(project.Project.load(a.project), a.content, a.out)
        except (project.MissingInput, OSError, ValueError) as e:
            print(f"preview failed: {e}", file=sys.stderr)
            return 2
        return 0
    if a.cmd == "devices":
        for cam in configs.load_devices(a.file):
            print(f"{cam.name} | {cam.width}x{cam.height} f=({cam.fx},{cam.fy})")
    else:
        for s in configs.load_content_spaces(a.file):
            print(f"{s.name} | {s.width}x{s.height} {s.kind} models={s.models3d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
