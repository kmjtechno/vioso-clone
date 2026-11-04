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
    v = sub.add_parser("preview", help="software-render content through a calibrated project mesh")
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
    sub.add_parser("gui", help="launch the optional PySide6 project editor")
    still = sub.add_parser("present-preview", help="opt-in bounded calibrated still on a projector")
    still.add_argument("project", help="calibrated clone-format JSON project")
    still.add_argument("content", help="source image to warp")
    still.add_argument("--projector-x", type=int, required=True)
    still.add_argument("--projector-y", type=int, required=True)
    still.add_argument("--duration-ms", type=int, default=5000, help="1..30000 ms")
    still.add_argument("--confirm-display", action="store_true")
    a = ap.parse_args(argv)
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
