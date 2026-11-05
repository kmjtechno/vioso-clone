"""Safe entrypoint for the independent portable Windows VIOSO Clone GUI.

A frozen executable is an UNSIGNED alpha QA build, not vendor VIOSO 7.
No hardware access occurs during --self-test or --version. Physical camera
operation still requires a separate per-action explicit GUI confirmation.
"""
from __future__ import annotations

import sys

from vclone import __version__


def portable_main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--version"]:
        print("KMJ VIOSO Clone " + __version__)
        return 0
    if args == ["--self-test"]:
        # This flag is intentionally no-I/O and safe for automated Windows CI.
        # On a user desktop it creates and destroys an OFFSCREEN Qt window.
        import os

        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtWidgets import QApplication
        from vclone.gui import MainWindow

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        try:
            menus = [item.menu() for item in window.menuBar().actions()]
            labels = {action.text() for menu in menus if menu is not None
                      for action in menu.actions()}
            required = {
                "Compare two-projector seam (offline)...",
                "Check camera profile (offline)...",
                "Check Windows projector rig (read-only)...",
                "Probe selected camera (explicit consent)...",
                "Connect ONVIF camera (no saved credentials)...",
            }
            if not required.issubset(labels):
                return 3
            if window._camera_probe_worker is not None:
                return 4
            if window.session.dirty:
                return 5
            return 0
        finally:
            window.close()
    if args:
        # Reject unexpected arguments before making a QApplication or touching
        # camera/device code. Do not accept implicit physical action flags.
        return 2
    from vclone.gui import main as gui_main

    return gui_main([sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(portable_main())
