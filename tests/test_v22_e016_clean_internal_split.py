import json
from pathlib import Path


def test_clean_internal_split_has_no_development_overlap():
    root = Path(__file__).resolve().parents[1]
    split = json.loads((root / "v22_e016_clean_internal_split.json").read_text())
    assert split["total_samples"] == 199
    assert split["development_excluded_samples"] == 27
    assert split["clean_pool_samples"] == 172
    assert split["fit_samples"] + split["internal_validation_samples"] == 172
    assert split["development_overlap"] is False
    assert split["hidden_test_overlap"] is False
    assert all(split["family_counts"]["validation"].values())
