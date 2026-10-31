

def test_manual_spacing_and_trailing_separators():
    from vclone import cmdline
    r = cmdline.parse(['/Q: "Edit MRD; CloseAfter=yes"', '/F: "Player"', '/L: "a b.sps"'])
    assert r.values["step"] == "Edit MRD" and r.close_after is True
    assert r.values["profile"] == "Player" and r.values["sps"] == "a b.sps"
    assert cmdline.parse(['/Q:"Export;CloseAfter=no;"']).close_after is False
