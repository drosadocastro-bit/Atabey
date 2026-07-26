import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_clean_checkpoint_contract_is_leakage_safe():
    contract = json.loads(
        (ROOT / "tests/fixtures/v22_e016_clean_secondary_checkpoint.json").read_text()
    )
    assert contract["expected_total_competition_samples"] == 199
    assert contract["expected_clean_training_samples"] == 172
    assert contract["expected_held_out_development_samples"] == 27
    assert contract["expected_held_out_development_events"] == 46
    assert contract["development_labels_used_for_fit_or_selection"] is False
    assert contract["hidden_test_labels_used_for_fit_or_selection"] is False
    assert contract["graph_mutation"] is False
    assert contract["assignment"] is False
    assert contract["full_199_authorized"] is False
