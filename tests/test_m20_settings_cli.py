"""Safe, non-destructive clone settings XML CLI regressions."""
from vclone import projectxml
from vclone.__main__ import main


def test_new_and_check(tmp_path, capsys):
    dest = tmp_path / "settings.xml"
    assert main(["settings-new", str(dest), "--name", "Room <A> & B"]) == 0
    assert projectxml.from_xml(dest.read_text(encoding="utf-8")).name == "Room <A> & B"
    assert main(["settings-check", str(dest)]) == 0
    out = capsys.readouterr().out
    assert "clone_settings=VALID" in out
    assert "native_vioso_sps_compatible=NO" in out


def test_new_refuses_existing_owner_file(tmp_path, capsys):
    dest = tmp_path / "owner.xml"
    dest.write_text("OWNER EXISTING", encoding="utf-8")
    assert main(["settings-new", str(dest)]) == 2
    assert dest.read_text(encoding="utf-8") == "OWNER EXISTING"
    assert "refused" in capsys.readouterr().err


def test_new_invalid_name_does_not_write(tmp_path):
    dest = tmp_path / "bad.xml"
    assert main(["settings-new", str(dest), "--name", "bad\nname"]) == 2
    assert not dest.exists()


def test_check_rejects_invalid_xml_without_mutation(tmp_path, capsys):
    dest = tmp_path / "bad.xml"
    dest.write_text("<VIOSO><unknown/></VIOSO>", encoding="utf-8")
    assert main(["settings-check", str(dest)]) == 2
    assert dest.read_text(encoding="utf-8") == "<VIOSO><unknown/></VIOSO>"
    assert "refused" in capsys.readouterr().err


def test_missing_file_is_not_created(tmp_path):
    dest = tmp_path / "missing.xml"
    assert main(["settings-check", str(dest)]) == 2
    assert not dest.exists()


def test_oversized_file_refused_before_parse(tmp_path, capsys):
    dest = tmp_path / "large.xml"
    dest.write_bytes(b"x" * (projectxml.MAX_XML_BYTES + 1))
    assert main(["settings-check", str(dest)]) == 2
    assert "exceeds" in capsys.readouterr().err


def test_new_file_is_validated_without_hardware(tmp_path):
    dest = tmp_path / "clone.xml"
    assert main(["settings-new", str(dest)]) == 0
    assert dest.is_file()
