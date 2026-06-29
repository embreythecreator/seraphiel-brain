from seraphiel_cli.absorb import detect


def test_newer_tags_orders_date_tags():
    tags = ["v2026.6.5", "v2026.6.19", "v2026.5.28", "v2026.6.19"]
    out = detect.newer_tags("v2026.6.5", tags)
    assert out == ["v2026.6.19"]


def test_newer_tags_handles_dotted_patch():
    out = detect.newer_tags("v2026.5.29", ["v2026.5.29.2", "v2026.5.29"])
    assert out == ["v2026.5.29.2"]


def test_no_newer_returns_empty():
    assert detect.newer_tags("v2026.6.19", ["v2026.6.5", "v2026.6.19"]) == []
