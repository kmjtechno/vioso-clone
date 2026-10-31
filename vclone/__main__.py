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
    a = ap.parse_args(argv)
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
