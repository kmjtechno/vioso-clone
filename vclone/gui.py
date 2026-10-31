"""Thin PySide6 front end over gui_model.Session. PySide6 is imported lazily by main()."""
import sys

from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QMainWindow, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from .gui_model import Session, SessionError


class MainWindow(QMainWindow):
    def __init__(self, session=None):
        super().__init__()
        self.session = session or Session()
        central = QWidget()
        self.setCentralWidget(central)
        col = QVBoxLayout(central)
        row = QHBoxLayout()
        col.addLayout(row)
        self.step_buttons = []
        for name, ok in self.session.steps():
            b = QPushButton(name)
            b.setEnabled(ok)
            if not ok:
                b.setToolTip("not implemented in the clone yet")
            b.clicked.connect(lambda _=False, n=name: self.run_step(n))
            row.addWidget(b)
            self.step_buttons.append(b)
        self.log_view = QPlainTextEdit(readOnly=True)
        col.addWidget(self.log_view)
        m = self.menuBar().addMenu("&File")
        m.addAction("&Open...", self.open_project)
        m.addAction("&Save", self.save_project)
        m.addAction("Save &As...", self.save_project_as)
        m.addAction("&Quit", self.close)
        self.refresh()

    def refresh(self):
        s = self.session
        self.setWindowTitle(f"VIOSO Clone - {s.project.name}{' *' if s.dirty else ''}")
        self.log_view.setPlainText("\n".join(s.log))

    def _guard(self, fn, *a):
        try:
            fn(*a)
        except SessionError as e:
            QMessageBox.warning(self, "VIOSO Clone", str(e))
        self.refresh()

    def run_step(self, name):
        self._guard(self.session.run, name)

    def open_project(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open project", "", "Project (*.json)")
        if f:
            self._guard(self.session.open, f)

    def save_project(self):
        if self.session.path is None:
            return self.save_project_as()
        self._guard(self.session.save)

    def save_project_as(self):
        f, _ = QFileDialog.getSaveFileName(self, "Save project", "", "Project (*.json)")
        if f:
            self._guard(self.session.save, f)


def main(argv=None):
    app = QApplication(argv or sys.argv)
    w = MainWindow()
    w.show()
    return app.exec()
