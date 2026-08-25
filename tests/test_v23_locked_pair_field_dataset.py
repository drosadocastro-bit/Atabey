import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_v23_locked_pair_field_dataset.py"


def _module():
    spec = importlib.util.spec_from_file_location("locked_pair_field_dataset", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sparse_pair_splat_is_symmetric_and_mass_two():
    module = _module()
    first = module._sparse_splat((2.25, -3.5, 4.75))
    assert sum(entry["weight"] for entry in first) == pytest.approx(1.0)

    class Detection:
        def __init__(self, position):
            self.position_um = position

    parent = Detection((10.0, 10.0, 10.0))
    child_1 = Detection((12.25, 6.5, 14.75))
    child_2 = Detection((6.0, 12.5, 8.75))
    forward = module._pair_sparse_splat(parent, child_1, child_2)
    reverse = module._pair_sparse_splat(parent, child_2, child_1)

    assert forward == reverse
    assert sum(entry["weight"] for entry in forward) == pytest.approx(2.0)


def test_fp_selection_is_hash_bounded_and_never_selects_unknown():
    module = _module()
    rows = [
        {"event_id": "event", "action_id": "tp", "official_label": "official_tp", "selected_for_training": False},
        *[
            {"event_id": "event", "action_id": f"fp-{index}", "official_label": "official_fp", "selected_for_training": False}
            for index in range(100)
        ],
        {"event_id": "event", "action_id": "unknown", "official_label": "official_unsupported", "selected_for_training": False},
    ]
    module._select_training_actions(rows)

    assert rows[0]["selected_for_training"] is True
    assert sum(row["selected_for_training"] for row in rows[1:101]) == 64
    assert rows[-1]["selected_for_training"] is False


def test_dataset_readiness_requires_tp_fp_support_without_unknown_relabeling():
    module = _module()
    contract = json.loads(
        (ROOT / "tests/fixtures/v23_bounded_pair_field_ranker.json").read_text()
    )
    events = []
    for fold, family, count in (
        (1, "44b6", 5),
        (1, "6bba", 5),
        (2, "44b6", 5),
        (2, "6bba", 5),
        (3, "44b6", 5),
        (3, "6bba", 5),
    ):
        for index in range(count):
            events.append(
                {
                    "event_id": f"{fold}-{family}-{index}",
                    "fold": fold,
                    "family": family,
                    "official_tp": 3 if len(events) < 2 else 1,
                    "official_fp": 2,
                }
            )
    events = events[:29]
    events[0]["official_tp"] = 60
    result = module._readiness(events, contract)

    assert result["gates"]["exact_tp_events"] is True
    assert result["gates"]["exact_tp_action_variants"] is True
    assert result["gates"]["events_with_tp_and_fp_overall"] is True
    assert result["gates"]["events_with_tp_and_fp_per_family"] is True
    assert result["gates"]["events_with_tp_and_fp_per_training_complement"] is True
