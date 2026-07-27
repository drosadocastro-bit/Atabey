from pathlib import Path


def test_early_stop_source_helper_is_present():
    root = Path(__file__).resolve().parents[1]
    helper = root / "scripts/prepare_v22_e016_early_stop_source.py"
    text = helper.read_text(encoding="utf-8")
    assert "--patience" in text
    assert "--min-delta" in text
    assert "Early stopping at epoch" in text
