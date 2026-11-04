"""Script engine: runs XML task scripts (<VIOSO><define/><task/></VIOSO>).

Written from the public script reference, not from VIOSO code. Actions that need real
devices, renderers, networks or OS control raise UnsupportedAction instead of pretending.
"""
import re
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .project import MissingInput, NotImplementedStep, Project, render_preview, run_step

ACTIONS = {"condition", "configure", "connect", "control", "create", "destroy", "destroyall", "disconnect",
           "execute", "ipc", "load", "manipulate", "playlist", "refresh", "refreshall", "render", "recover",
           "save", "send", "start", "startall", "stop", "stopall", "transfer", "wait"}


class ScriptError(Exception):
    pass


class UnsupportedAction(ScriptError):
    pass


class ScriptAborted(ScriptError):
    pass


class _Finish(Exception):
    pass


@dataclass
class Context:
    project: Project | None = None
    base_dir: Path = Path(".")
    env: dict = field(default_factory=dict)
    sleep: object = time.sleep
    depth: int = 0


_CAST = {"i": int, "f": float, "d": float, "s": str}


def parse_env(text):
    """'name=value{,type};...' -> dict. Types: i, f, d, s (default)."""
    env = {}
    for item in filter(None, (t.strip() for t in text.split(";"))):
        if "=" not in item:
            raise ScriptError(f"bad variable '{item}'")
        name, val = item.split("=", 1)
        typ = "s"
        head, sep, tail = val.rpartition(",")
        if sep and tail.strip() in _CAST:
            val, typ = head, tail.strip()
        try:
            env[name.strip()] = _CAST[typ](val)
        except ValueError:
            raise ScriptError(f"variable '{name}' is not of type {typ}: {val!r}") from None
    return env


def substitute(text, env):
    def rep(m):
        source, name = m.group(1), m.group(2)
        if source != "ENV" or name not in env:
            raise ScriptError(f"undefined variable ${source}${name}$")
        return str(env[name])
    return re.sub(r"\$([A-Za-z0-9_]+)\$([A-Za-z0-9_ ]+)\$", rep, text)


def _attrs(el, ctx):
    return {k: substitute(v, ctx.env) for k, v in el.attrib.items()}


def _params(task, defines, ctx):
    """Merged <param> attributes: the define named by use=, then inline params override."""
    out = {}
    use = task.get("use")
    if use is not None:
        if use not in defines:
            raise ScriptError(f"task uses undefined define '{use}'")
        for p in defines[use].findall("param"):
            out.update(_attrs(p, ctx))
    for p in task.findall("param"):
        out.update(_attrs(p, ctx))
    return out


def _child(task, defines, name, ctx):
    for src in (task, defines.get(task.get("use"))):
        if src is not None and src.find(name) is not None:
            return _attrs(src.find(name), ctx)
    return {}


def _path(ctx, name):
    p = Path(name)
    return p if p.is_absolute() else ctx.base_dir / p


def _need(params, key, what):
    if key not in params:
        raise ScriptError(f"{what} needs parameter '{key}'")
    return params[key]


def _flag(params, key):
    return params.get(key, "0") not in ("0", "", "false")


# --- handlers: (task, defines, ctx, typ, subtyp) ---------------------------------------

def _timer(task, defines, ctx, typ, sub):
    ms = float(_need(_params(task, defines, ctx), "duration", "Timer"))
    ctx.sleep(ms / 1000.0)


def _exec_script(task, defines, ctx, typ, sub):
    if ctx.depth >= 16:
        raise ScriptError("script nesting too deep")
    name = _need(_params(task, defines, ctx), "name", "Execute script")
    f = _path(ctx, name)
    if not f.is_file():
        raise ScriptError(f"script not found: {f}")
    ctx.depth += 1
    try:
        _run_text(f.read_text(encoding="utf-8", errors="replace"), ctx)
    finally:
        ctx.depth -= 1


def _exec_step(task, defines, ctx, typ, sub):
    """Clone extension: run one /Q: step on the current project."""
    name = _need({**task.attrib, **_params(task, defines, ctx)}, "name", "Execute step")
    if ctx.project is None:
        raise ScriptError("no project loaded")
    try:
        run_step(ctx.project, name)
    except (MissingInput, ValueError) as e:
        raise ScriptError(str(e)) from e
    except NotImplementedStep as e:
        raise UnsupportedAction(str(e)) from e


def _exec_preview(task, defines, ctx, typ, sub):
    """Clone extension: software preview of the calibrated mesh (no display output)."""
    params = _params(task, defines, ctx)
    content, out = _need(params, "content", "Execute preview"), _need(params, "out", "Execute preview")
    if ctx.project is None:
        raise ScriptError("no project loaded")
    try:
        render_preview(ctx.project, _path(ctx, content), _path(ctx, out))
    except (MissingInput, ValueError, OSError) as e:
        # Preview's exclusive-create rejection must remain a ScriptError to
        # XML automation callers; never let it overwrite an existing owner PNG.
        raise ScriptError(str(e)) from e


def _execute(task, defines, ctx, typ, sub):
    if typ in ("timer", "sleep"):
        return _timer(task, defines, ctx, typ, sub)
    if typ == "file" and sub == "script":
        return _exec_script(task, defines, ctx, typ, sub)
    if typ == "preview":
        return _exec_preview(task, defines, ctx, typ, sub)
    if typ == "step":
        return _exec_step(task, defines, ctx, typ, sub)
    raise UnsupportedAction(f"Execute {typ}/{sub} is not supported")


def _transfer(task, defines, ctx, typ, sub):
    if typ != "file":
        raise UnsupportedAction(f"Transfer {typ} is not supported")
    src = _need(_child(task, defines, "from", ctx), "file", "Transfer from")
    dst = _need(_child(task, defines, "to", ctx), "file", "Transfer to")
    s = _path(ctx, src)
    if not s.is_file():
        raise ScriptError(f"transfer source missing: {s}")
    d = _path(ctx, dst)
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(s, d)


def _load(task, defines, ctx, typ, sub):
    if typ != "sps":
        raise UnsupportedAction(f"Load {typ} is not supported")
    f = _path(ctx, _need(_params(task, defines, ctx), "file", "Load"))
    if not f.is_file():
        raise ScriptError(f"project file missing: {f}")
    try:
        ctx.project = Project.load(f)
    except (ValueError, TypeError, KeyError) as e:
        raise ScriptError(f"cannot read project {f}: {e}") from e


def _save(task, defines, ctx, typ, sub):
    if typ != "sps":
        raise UnsupportedAction(f"Save {typ} is not supported")
    if ctx.project is None:
        raise ScriptError("no project to save")
    params = _params(task, defines, ctx)
    f = _path(ctx, _need(params, "file", "Save"))
    if _flag(params, "bMustNotExist") and f.exists():
        raise ScriptError(f"refusing to overwrite {f}")
    ctx.project.save(f)


_CONDS = {
    "fileexists": lambda a, ctx: _path(ctx, a.get("file", "")).exists(),
    "filenotexists": lambda a, ctx: not _path(ctx, a.get("file", "")).exists(),
}


def _conditions_met(task, defines, ctx):
    block = task.find("conditions")
    if block is None:
        return True
    results = []
    for c in block:
        a = _attrs(c, ctx)
        fn = _CONDS.get(a.get("tCondition", "").lower())
        if fn is None:
            raise UnsupportedAction(f"condition '{a.get('tCondition')}' is not supported")
        results.append(fn(a, ctx))
    if not results:
        return True
    return all(results) if block.get("bAll", "1") not in ("0", "false") else any(results)


def _apply_option(task, ctx, wanted):
    for o in task.findall("option"):
        if o.get("tOption") == wanted:
            act = o.get("tAction", "continue")
            if act == "abort":
                raise ScriptAborted("aborted by script option")
            if act == "finish":
                raise _Finish
            return


def _wait(task, defines, ctx, typ, sub):
    # Evaluated once: the clone has no background events to wait for.
    _apply_option(task, ctx, "yes" if _conditions_met(task, defines, ctx) else "no")


def _ipc(task, defines, ctx, typ, sub):
    perform = task.find("perform")
    if perform is not None and perform.get("tAction") == "finish":
        raise _Finish
    raise UnsupportedAction(f"IPC {typ} is not supported")


_HANDLERS = {"execute": _execute, "transfer": _transfer, "load": _load, "save": _save,
             "wait": _wait, "condition": _wait, "ipc": _ipc}


def _run_text(text, ctx):
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ScriptError(f"malformed script: {e}") from e
    if root.tag != "VIOSO":
        raise ScriptError("root element must be <VIOSO>")
    defines = {d.get("name"): d for d in root.findall("define")}
    try:
        for task in root.findall("task"):
            action = (task.get("action") or "").lower()
            if action not in ACTIONS:
                raise ScriptError(f"unknown action '{task.get('action')}'")
            h = _HANDLERS.get(action)
            if h is None:
                raise UnsupportedAction(f"action '{task.get('action')}' needs devices/renderers not in the clone")
            h(task, defines, ctx, (task.get("typ") or "").lower(), (task.get("subtyp") or "").lower())
    except _Finish:
        pass


def run_script(text, env=None, project=None, base_dir=".", sleep=time.sleep):
    """Run script text. env: dict or 'a=1,i;b=x' string. Returns the Context (project may change)."""
    if isinstance(env, str):
        env = parse_env(env)
    ctx = Context(project, Path(base_dir), dict(env or {}), sleep)
    _run_text(text, ctx)
    return ctx
