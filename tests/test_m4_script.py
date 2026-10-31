import pytest

from vclone import script
from vclone.project import Project


def wrap(body):
    return f'<?xml version="1.0"?><VIOSO><File version="1.0.0"/>{body}</VIOSO>'


def test_env_parsing_types():
    env = script.parse_env("a=3,i;b=1.5,f;c=hi;d=2,d;e=x y,s")
    assert env == {"a": 3, "b": 1.5, "c": "hi", "d": 2.0, "e": "x y"}
    with pytest.raises(script.ScriptError):
        script.parse_env("a=zz,i")
    with pytest.raises(script.ScriptError):
        script.parse_env("novalue")


def test_substitution():
    env = {"n": 7, "s": "ab"}
    assert script.substitute("x$ENV$s$y", env) == "xaby"
    assert script.substitute("$ENV$n$", env) == "7"
    with pytest.raises(script.ScriptError):
        script.substitute("$ENV$missing$", env)


def test_transfer_file_copies_and_overwrites(tmp_path):
    (tmp_path / "a.txt").write_text("one")
    (tmp_path / "b.txt").write_text("old")
    xml = wrap('<define name="t" typ="Transfer"><from file="$ENV$src$"/><to file="b.txt"/></define>'
               '<task action="Transfer" typ="file" use="t"/>')
    script.run_script(xml, env={"src": "a.txt"}, base_dir=tmp_path)
    assert (tmp_path / "b.txt").read_text() == "one"


def test_transfer_missing_source_fails(tmp_path):
    xml = wrap('<task action="Transfer" typ="file"><from file="nope"/><to file="x"/></task>')
    with pytest.raises(script.ScriptError):
        script.run_script(xml, base_dir=tmp_path)


def test_timer_uses_injected_sleep():
    slept = []
    xml = wrap('<define name="w" typ="Common"><param duration="250"/></define>'
               '<task action="Execute" typ="Timer" use="w"/>')
    script.run_script(xml, sleep=slept.append)
    assert slept == [0.25]


def test_inline_param_overrides_define():
    slept = []
    xml = wrap('<define name="w" typ="Common"><param duration="250"/></define>'
               '<task action="Execute" typ="Timer" use="w"><param duration="10"/></task>')
    script.run_script(xml, sleep=slept.append)
    assert slept == [0.01]


def test_undefined_use_fails():
    with pytest.raises(script.ScriptError):
        script.run_script(wrap('<task action="Execute" typ="Timer" use="ghost"/>'))


def test_unsupported_actions_fail_loudly():
    for act, typ in (("Execute", "OS"), ("Connect", "core"), ("Render", "x"), ("Send", "TCP")):
        with pytest.raises(script.UnsupportedAction):
            script.run_script(wrap(f'<task action="{act}" typ="{typ}"/>'))
    with pytest.raises(script.ScriptError):
        script.run_script(wrap('<task action="Bogus" typ="x"/>'))


def test_nested_script_and_load_save_project(tmp_path):
    inner = wrap('<define name="f" typ="Common"><param file="out.json"/></define>'
                 '<task action="Save" typ="sps" use="f"/>')
    (tmp_path / "inner.vs").write_text(inner)
    outer = wrap('<define name="s" typ="App"><param name="inner.vs"/></define>'
                 '<task action="Execute" typ="File" subtyp="script" use="s"/>')
    proj = Project("p")
    script.run_script(outer, project=proj, base_dir=tmp_path)
    assert Project.load(tmp_path / "out.json").name == "p"
    load = wrap('<define name="f" typ="Common"><param file="out.json"/></define>'
                '<task action="Load" typ="sps" use="f"/>')
    ctx = script.run_script(load, project=Project("other"), base_dir=tmp_path)
    assert ctx.project.name == "p"


def test_load_must_not_exist(tmp_path):
    Project("p").save(tmp_path / "o.json")
    xml = wrap('<task action="Save" typ="sps"><param file="o.json" bMustNotExist="1"/></task>')
    with pytest.raises(script.ScriptError):
        script.run_script(xml, project=Project("p"), base_dir=tmp_path)


def test_wait_condition_abort_vs_continue(tmp_path):
    xml = wrap('<task action="Wait" typ="Condition"><conditions bAll="1">'
               '<cond tCondition="FileExists" file="nofile"/></conditions>'
               '<option tOption="no" tAction="abort"/></task>'
               '<task action="Execute" typ="Timer"><param duration="1"/></task>')
    with pytest.raises(script.ScriptAborted):
        script.run_script(xml, base_dir=tmp_path, sleep=lambda s: None)
    (tmp_path / "nofile").write_text("x")
    slept = []
    script.run_script(xml, base_dir=tmp_path, sleep=slept.append)
    assert slept == [0.001]


def test_finish_stops_cleanly():
    xml = wrap('<task action="IPC" typ="Common"><perform tAction="finish" tTask="guided" iError="0"/></task>'
               '<task action="Execute" typ="Timer"><param duration="1"/></task>')
    slept = []
    script.run_script(xml, sleep=slept.append)
    assert slept == []


def test_calibrate_via_project_step_reports_missing_input():
    xml = wrap('<task action="Create" typ="Calib" subtyp="calibrate"/>')
    with pytest.raises(script.UnsupportedAction):
        script.run_script(xml, project=Project("p"))
    xml = wrap('<task action="Execute" typ="Step" name="Calibrate"/>')
    with pytest.raises(script.ScriptError):
        script.run_script(xml, project=Project("p"))


def test_malformed_xml():
    with pytest.raises(script.ScriptError):
        script.run_script("<VIOSO><task></VIOSO>")
    with pytest.raises(script.ScriptError):
        script.run_script("<root/>")
