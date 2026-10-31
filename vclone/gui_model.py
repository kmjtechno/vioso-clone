"""Qt-free session model behind the GUI: project load/save, step runner, log. Fully unit-testable."""
from pathlib import Path

from .cmdline import STEPS
from .project import _IMPL, MissingInput, NotImplementedStep, Project, run_step


class SessionError(Exception):
    pass


class Session:
    def __init__(self, project=None):
        self.project = project or Project()
        self.path = None
        self.dirty = False
        self.log = []

    def _note(self, msg):
        self.log.append(msg)

    def rename(self, name):
        self.project.name = name
        self.dirty = True
        self._note(f"project renamed to {name}")

    def open(self, path):
        try:
            proj = Project.load(path)
        except (OSError, ValueError, TypeError, KeyError) as e:
            raise SessionError(f"cannot open {path}: {e}") from e
        self.project, self.path, self.dirty = proj, Path(path), False
        self._note(f"opened {path}")

    def save(self, path=None):
        target = Path(path) if path else self.path
        if target is None:
            raise SessionError("no file path: use save as")
        try:
            self.project.save(target)
        except OSError as e:
            raise SessionError(f"cannot save {target}: {e}") from e
        self.path, self.dirty = target, False
        self._note(f"saved {target}")

    def steps(self):
        """[(step name, implemented)] in command-line order."""
        return [(s, s in _IMPL) for s in sorted(STEPS)]

    def run(self, step):
        try:
            run_step(self.project, step)
        except MissingInput as e:
            self._note(f"{step} failed: missing input: {e}")
            raise SessionError(f"missing input: {e}") from e
        except NotImplementedStep as e:
            self._note(f"{step} failed: not implemented")
            raise SessionError(f"not implemented: {e}") from e
        except ValueError as e:
            self._note(f"{step} failed: {e}")
            raise SessionError(str(e)) from e
        self.dirty = True
        self._note(f"{step} done")
