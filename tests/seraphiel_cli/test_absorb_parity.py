from seraphiel_cli.absorb import rename_map, parity_report


def test_swap_text_hermes_and_attribution():
    out = rename_map.swap_text("Hermes Agent, created by Hermes", "seraphiel_cli/x.py")
    assert "Seraphiel Brain" in out
    assert "created by Embrey The Creator" in out
    assert "Hermes" not in out


def test_legal_file_keeps_nous_attribution():
    out = rename_map.swap_text("Copyright (c) 2025 Nous Research", "LICENSE")
    assert out == "Copyright (c) 2025 Nous Research"


def test_report_flags_conflict_markers(monkeypatch):
    monkeypatch.setattr(parity_report, "names", lambda t: set())
    monkeypatch.setattr(parity_report, "diff_names", lambda a, b: [])
    monkeypatch.setattr(parity_report, "grep_conflict_markers", lambda t: ["a.py"])
    monkeypatch.setattr(parity_report, "grep_stray", lambda t: [])
    r = parity_report.report("m", "t", "HEAD")
    assert r["ready"] is False and r["conflicts"] == ["a.py"]
