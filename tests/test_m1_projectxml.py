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
