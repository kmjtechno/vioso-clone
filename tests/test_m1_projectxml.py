import pytest

from vclone import projectxml as px


def test_defaults_match_documented_values():
    s = px.ProjectSettings()
    assert (s.type, s.state, s.method) == (1, 0, 1)
    assert s.spspath == "_Startup.sps" and s.mrdpath == "_Startup.mrd"
    assert s.screen.radius == 1000 and s.screen.width == 3200 and s.screen.height == 2000
    assert s.screen.leftangle == -90 and s.screen.topangle == 45


def test_roundtrip_preserves_every_field():
    s = px.ProjectSettings(name="dome A", type=3, state=2, method=2, spspath="C:/x/a.sps")
    s.screen.type = 2
    s.screen.radius = 2500.5
    back = px.from_xml(px.to_xml(s))
    assert back == s


def test_xml_shape_is_viosoproject_with_property_nodes():
    root = px.to_xml(px.ProjectSettings(name="p"))
    assert root.startswith("<?xml") and "<VIOSO>" in root and "<project " in root
    assert 'name="spspath"' in root


@pytest.mark.parametrize("field,value", [
    ("type", 6), ("type", -1), ("state", 4), ("state", -2), ("method", 0), ("method", 3),
])
def test_enum_out_of_range_is_rejected(field, value):
    with pytest.raises(ValueError, match=field):
        px.ProjectSettings(**{field: value})


@pytest.mark.parametrize("field,value", [
    ("radius", 0), ("width", -5), ("radius", 1e8), ("longitudestep", 0.05),
    ("leftangle", 5), ("topangle", -3), ("outside", 2), ("type", 9),
])
def test_screen_value_outside_range_is_rejected(field, value):
    with pytest.raises(ValueError, match=field):
        px.ScreenParams(**{field: value})


def test_nonfinite_screen_value_rejected():
    with pytest.raises(ValueError, match="radius"):
        px.ScreenParams(radius=float("nan"))


@pytest.mark.parametrize("xml", [
    "", "<VIOSO/>", "<VIOSO><project version='9.9' creator='x'/></VIOSO>",
    "<VIOSO><project version='1.0' creator='x'><property name='type' type='int'>zz</property></project></VIOSO>",
    "<notviosO/>",
])
def test_malformed_or_unsupported_input_fails_closed(xml):
    with pytest.raises(ValueError):
        px.from_xml(xml)


def test_unknown_property_names_are_rejected_not_ignored():
    xml = px.to_xml(px.ProjectSettings()).replace('name="state"', 'name="mystery"')
    with pytest.raises(ValueError, match="mystery"):
        px.from_xml(xml)


def test_xml_escaped_values_roundtrip():
    s = px.ProjectSettings(name='Room <A> & "B"', spspath=r"E:\KMJ\Codex\VIOSO-Clone\demo.sps")
    assert px.from_xml(px.to_xml(s)) == s


def test_duplicate_empty_screen_fails_closed():
    s = px.to_xml(px.ProjectSettings())
    start = s.index('    <property name="screen" type="composite">')
    end = s.index("    </property>", start) + len("    </property>")
    empty = '<property name="screen" type="composite"/>'
    doubled = s[:start] + empty + empty + s[end:]
    with pytest.raises(ValueError, match="duplicate property screen"):
        px.from_xml(doubled)


@pytest.mark.parametrize("replace", [
    ('<VIOSO>', '<VIOSO origin="owner">'),
    ('<project version=', '<project other="unexpected" version='),
    ('<property name="type" type="int">', '<property name="type" type="float">'),
    ('<property name="screen" type="composite">', '<property name="screen" type="string">'),
    ('<property name="radius" type="float">', '<property name="radius" type="string">'),
    ('</VIOSO>', '<surprise/></VIOSO>'),
])
def test_unexpected_structure_and_types_fail_closed(replace):
    src = px.to_xml(px.ProjectSettings())
    old, new = replace
    assert old in src
    with pytest.raises(ValueError):
        px.from_xml(src.replace(old, new, 1))


def test_no_ignored_nonproperty_nodes():
    src = px.to_xml(px.ProjectSettings()).replace("</project>", "<unknown/> </project>")
    with pytest.raises(ValueError):
        px.from_xml(src)


def test_reject_oversized_input_before_xml_parse():
    payload = '<VIOSO>' + 'X' * (px.MAX_XML_BYTES + 1) + '</VIOSO>'
    with pytest.raises(ValueError, match="exceeds"):
        px.from_xml(payload)


def test_disallow_entity_declaration():
    xml = '<!DOCTYPE VIOSO [<!ENTITY x "owner">]><VIOSO><project version="1.0" creator="x"/></VIOSO>'
    with pytest.raises(ValueError, match="DTD"):
        px.from_xml(xml)
