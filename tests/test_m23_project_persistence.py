"""M23 atomic project persistence: never truncate existing owner data on failure."""
import json
import os

import pytest

from vclone import project
from vclone.project import Project


def test_atomic_roundtrip_and_no_pending_files(tmp_path):
    path = tmp_path / "room.json"
    p = Project("room", scan={"proj_size": [8, 6]}, result={"coverage": 0.8})
    p.save(path)
    assert Project.load(path).name == "room"
    assert Project.load(path).scan == {"proj_size": [8, 6]}
    assert list(tmp_path.glob(".*.pending")) == []


def test_replacing_own_previous_project_does_not_truncate(tmp_path):
    path = tmp_path / "room.json"
    Project("first").save(path)
    Project("second").save(path)
    assert Project.load(path).name == "second"
    assert list(tmp_path.glob(".*.pending")) == []


def test_invalid_nonfinite_state_cannot_damage_existing_project(tmp_path):
    path = tmp_path / "owner.json"
    before = b"OWNER FILE UNTOUCHED"
    path.write_bytes(before)
    with pytest.raises(ValueError, match="Out of range float values"):
        Project("room", result={"coverage": float("nan")}).save(path)
    assert path.read_bytes() == before
    assert list(tmp_path.glob(".*.pending")) == []


def test_atomic_replace_failure_preserves_original_and_cleans_owned_stage(monkeypatch, tmp_path):
    path = tmp_path / "owner.json"
    original = b'{"name":"owner"}'
    path.write_bytes(original)

    def no_replace(_source, _target):
        raise PermissionError("simulated sharing violation")

    monkeypatch.setattr(project.os, "replace", no_replace)
    with pytest.raises(PermissionError, match="sharing violation"):
        Project("new").save(path)
    assert path.read_bytes() == original
    assert list(tmp_path.glob(".*.pending")) == []


def test_load_refuses_oversized_input(tmp_path):
    path = tmp_path / "huge.json"
    with path.open("wb") as f:
        f.truncate(32 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="32 MiB"):
        Project.load(path)


@pytest.mark.parametrize("content", [
    "[]", "null", "false", "42", '{"name":true}',
    '{"scan": [1, 2]}', '{"result": []}', '{"steps_done":"Calibrate"}',
    '{"coverage":NaN}', '{"camera":123}',
])
def test_load_rejects_invalid_root_or_field_types(tmp_path, content):
    path = tmp_path / "invalid.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        Project.load(path)


def test_load_refuses_symlink_and_save_does_not_follow_it(tmp_path):
    owner = tmp_path / "owner.json"
    Project("owner").save(owner)
    ref = tmp_path / "linked.json"
    try:
        ref.symlink_to(owner)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this runner")
    before = owner.read_bytes()
    with pytest.raises(ValueError, match="non-symlink"):
        Project.load(ref)
    with pytest.raises(ValueError, match="regular path"):
        Project("new").save(ref)
    assert owner.read_bytes() == before


def test_regular_valid_json_accepted_even_without_optional_fields(tmp_path):
    path = tmp_path / "minimal.json"
    path.write_text(json.dumps({"name": "minimal"}), encoding="utf-8")
    loaded = Project.load(path)
    assert loaded.name == "minimal"
    assert loaded.scan == {} and loaded.result == {}
