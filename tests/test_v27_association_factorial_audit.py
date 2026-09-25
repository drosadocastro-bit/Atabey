from copy import deepcopy

import numpy as np
import pytest

from atabey.tracking import association_factorial_audit as audit
from atabey.types import Detection


def node(name, t, y):
    return Detection(name, "synthetic", t, 0, y, 0, 0, y, 0)


def decisions(frame):
    assert frame["validity_failures"] == []
    return frame["rows"][0]["decisions"]


def test_motion_order_effect_is_separate_from_step_order_effect():
    frame = audit.audit_factorial_frame([node("s", 1, 0)],
        [node("outside", 2, 10), node("feasible", 2, 4)], {"s": node("p", 0, -8)})
    d = decisions(frame)
    assert {a: v["accepted_target_id"] for a, v in d.items()} == {
        "H": None, "M0": None, "M1": "feasible", "S0": "feasible", "S1": "feasible"}
    assert d["M0"]["selected_target_id"] == "outside"
    assert d["M0"]["gate_eligible_target_id"] is None
    assert d["M1"]["confidence"] == 1 - 4 / 9
    assert frame["rows"][0]["acceptance_interaction"] == -1


def test_step_nearest_can_fail_prediction_while_prefiltering_accepts():
    frame = audit.audit_factorial_frame([node("s", 1, 0)],
        [node("near-but-infeasible", 2, -2), node("feasible", 2, 4)], {"s": node("p", 0, -8)})
    d = decisions(frame)
    assert d["S0"]["rejection_reason"] == "prediction_gate"
    assert d["S0"]["accepted_target_id"] is None
    assert d["S1"]["accepted_target_id"] == "feasible"
    assert d["M0"]["accepted_target_id"] == d["M1"]["accepted_target_id"] == "feasible"
    assert frame["rows"][0]["acceptance_interaction"] == 1


def test_ranking_changes_identity_without_changing_acceptance_count():
    frame = audit.audit_factorial_frame([node("s", 1, 0)],
        [node("step", 2, 1), node("motion", 2, 4)], {"s": node("p", 0, -4)})
    d = decisions(frame)
    assert d["M0"]["accepted_target_id"] == "motion"
    assert d["S0"]["accepted_target_id"] == "step"
    c = frame["rows"][0]["contrasts"]["ranking_select_first"]
    assert c == {"selected_changed": True, "accepted_changed": True,
                 "removed_edge": ["s", "motion"], "added_edge": ["s", "step"], "accepted_delta": 0}
    assert frame["rows"][0]["acceptance_interaction"] == 0


def test_reverse_ownership_rejects_feasible_alternative_and_preserves_uniqueness():
    frame = audit.audit_factorial_frame([node("s", 1, 0), node("owner", 1, 3.9)],
        [node("outside", 2, 10), node("feasible", 2, 4)], {"s": node("p", 0, -8)})
    d = decisions(frame)
    assert d["S1"]["gate_eligible_target_id"] == "feasible"
    assert d["S1"]["reverse_owner_id"] == "owner"
    assert d["S1"]["rejection_reason"] == "reverse_mutuality"
    for arm in ["H", *audit.ARMS]:
        accepted = [r["decisions"][arm]["accepted_target_id"] for r in frame["rows"]
                    if r["decisions"][arm]["accepted_target_id"] is not None]
        assert len(accepted) == len(set(accepted))


def test_inclusive_radius_forward_ties_use_original_index_not_node_name():
    frame = audit.audit_factorial_frame([node("s", 1, 0)],
        [node("z-first", 2, 9), node("a-second", 2, -9)], {})
    d = decisions(frame)
    for arm in audit.ARMS:
        assert d[arm]["accepted_target_id"] == "z-first"
        assert d[arm]["confidence"] == 0
        assert d[arm]["rank_tie_indices"] == [0, 1]


def test_reverse_ties_are_observed_without_changing_ckdtree_owner():
    frame = audit.audit_factorial_frame([node("left", 1, -1), node("right", 1, 1)],
                                         [node("target", 2, 0)], {})
    assert not frame["validity_failures"]
    assert frame["reverse_ownership"][0]["tie_indices"] == [0, 1]
    owner = frame["reverse_ownership"][0]["owner_id"]
    for row in frame["rows"]:
        assert row["has_selected_reverse_tie"]
        for arm in audit.ARMS:
            assert (row["decisions"][arm]["accepted_target_id"] is not None) == (row["source_id"] == owner)


@pytest.mark.parametrize("targets", [[], [node("far", 2, 20)]])
def test_empty_or_infeasible_context_abstains_without_fallback(targets):
    frame = audit.audit_factorial_frame([node("s", 1, 0)], targets, {})
    d = decisions(frame)
    assert all(v["accepted_target_id"] is None for v in d.values())
    assert all(d[a]["selected_target_id"] is None for a in ("M1", "S1"))


def test_empty_source_frame_is_valid():
    frame = audit.audit_factorial_frame([], [node("t", 2, 0)], {})
    assert frame["rows"] == [] and frame["validity_failures"] == []


def test_absent_history_makes_motion_and_step_equivalent_without_ties():
    frame = audit.audit_factorial_frame([node("s", 1, 0)],
                                         [node("near", 2, 1), node("far", 2, 4)], {})
    d = decisions(frame)
    assert all(v["accepted_target_id"] == "near" for v in d.values())
    assert frame["rows"][0]["predecessor_id"] is None


def test_exact_input_preservation_and_replay():
    inputs = ([node("s", 1, 0)], [node("a", 2, 1), node("b", 2, 4)], {"s": node("p", 0, -4)})
    before = deepcopy(inputs)
    first = audit.audit_factorial_frame(*inputs)
    assert inputs == before
    assert first == audit.audit_factorial_frame(*inputs)
    assert first["input_sha256_before"] == first["input_sha256_after"]


def test_non_tie_numerical_discrepancy_is_preserved_not_called_a_tie(monkeypatch):
    real_tree = audit.cKDTree
    instances = []
    class PerturbedTree:
        def __init__(self, data):
            self.tree = real_tree(data)
            self.is_forward = not instances
            instances.append(self)
        def query(self, *args, **kwargs):
            distance, index = self.tree.query(*args, **kwargs)
            return (distance + 1e-5, index) if self.is_forward else (distance, index)
    monkeypatch.setattr(audit, "cKDTree", PerturbedTree)
    frame = audit.audit_factorial_frame([node("s", 1, 0)], [node("a", 2, 1)], {})
    checks = {f["check"] for f in frame["validity_failures"]}
    assert "h_m0_confidence_mismatch" in checks
    assert "H_executable_anchor_mismatch" in checks
    assert frame["rows"][0]["decisions"]["H"]["prediction_error_um"] == 1.00001


@pytest.mark.parametrize("value", [np.nan, np.inf])
def test_nonfinite_input_rejected(value):
    with pytest.raises(ValueError, match="Non-finite"):
        audit.audit_factorial_frame([node("s", 1, value)], [node("a", 2, 1)], {})


def test_nonadjacent_history_rejected():
    with pytest.raises(ValueError, match="Predecessor"):
        audit.audit_factorial_frame([node("s", 2, 0)], [node("a", 3, 1)], {"s": node("p", 0, -4)})


def test_counts_preserve_signed_contrasts_and_identity_changes():
    frame = audit.audit_factorial_frame([node("s", 1, 0)],
        [node("outside", 2, 10), node("feasible", 2, 4)], {"s": node("p", 0, -8)})
    counts = audit.summarize_rows(frame["rows"])
    assert counts["contrast::order_motion::added"] == 1
    assert counts["contrast::order_motion::removed"] == 0
    assert counts["contrast::order_motion::accepted_delta"] == 1
    assert counts["interaction_sum"] == -1
    assert counts["interaction::-1"] == 1
