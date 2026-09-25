from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_v26_a_gate_order_audit import inspect_frame, audit_sample, run_audit
from atabey.types import Detection, LineageEdge, LineageGraph
from atabey.tracking.unet_graph import graph_signature


def node(name, t, y):
    return Detection(name, "sample", t, 0, y, 0, 0, y, 0)


def test_filter_order_exposes_alternative_without_changing_motion_history():
    predecessor, source = node("p", 0, -8), node("s", 1, 0)
    targets = [node("outside-step", 2, 10), node("feasible", 2, 4)]
    history = {"s": predecessor}
    before = deepcopy((source, targets, history))
    row = inspect_frame([source], targets, history)[0]
    assert row["gate_order_exposed"]
    assert row["original_prediction_gate_passes"]
    assert not row["original_step_gate_passes"]
    assert row["feasible_count"] == 1
    assert row["baseline_accepted_target_id"] is None
    assert row["step_accepted_target_id"] == "feasible"
    assert (source, targets, history) == before


def test_available_alternative_can_still_fail_reverse_mutuality():
    source, competitor = node("s", 1, 0), node("other", 1, 3.9)
    row = inspect_frame(
        [source, competitor], [node("outside", 2, 10), node("feasible", 2, 4)],
        {"s": node("p", 0, -8)},
    )[0]
    assert row["gate_order_exposed"]
    assert row["step_selected_target_id"] == "feasible"
    assert row["step_selected_reverse_source_id"] == "other"
    assert row["step_accepted_target_id"] is None


def test_ranking_change_with_valid_original_is_not_gate_order_exposure():
    row = inspect_frame(
        [node("s", 1, 0)], [node("step-near", 2, 1), node("motion-near", 2, 4)],
        {"s": node("p", 0, -4)},
    )[0]
    assert not row["gate_order_exposed"]
    assert row["baseline_accepted_target_id"] == "motion-near"
    assert row["step_accepted_target_id"] == "step-near"


@pytest.mark.parametrize("target", [10.0, -10.0])
def test_no_feasible_alternative_is_not_order_exposure(target):
    row = inspect_frame([node("s", 1, 0)], [node("outside", 2, target)], {})[0]
    assert not row["gate_order_exposed"]
    assert row["feasible_count"] == 0
    assert row["step_accepted_target_id"] is None


def test_exact_radius_is_inclusive_and_ties_are_reported():
    row = inspect_frame(
        [node("s", 1, 0)], [node("a", 2, 9), node("b", 2, -9)], {},
    )[0]
    assert row["feasible_count"] == 2
    assert not row["gate_order_exposed"]
    assert row["step_accepted_target_id"] == "a"
    assert row["motion_minimum_tie"] and row["step_minimum_tie"]


def test_empty_target_frame_abstains():
    row = inspect_frame([node("s", 1, 0)], [], {})[0]
    assert row["target_count"] == 0
    assert not row["gate_order_exposed"]
    assert row["baseline_accepted_target_id"] is None
    assert row["step_accepted_target_id"] is None


def test_census_detects_frozen_graph_that_disagrees_with_executed_linker():
    graph = LineageGraph("sample", detections=[node("s", 0, 0), node("t", 1, 1)])
    before = graph_signature(graph)
    with pytest.raises(RuntimeError, match="Full frozen edge replay"):
        audit_sample({}, graph, {})
    assert graph_signature(graph) == before


def test_archived_recovery_overlap_does_not_modify_graph_or_history():
    graph = LineageGraph(
        "sample",
        detections=[node("p", 0, -8), node("s", 1, 0), node("outside", 2, 10), node("feasible", 2, 4)],
        edges=[LineageEdge("p", "s", confidence=1 - 8 / 9)],
    )
    record = {
        "sample_id": "sample",
        "v19_credited_v24_3_lost_edges": [{
            "ground_truth_source_id": 1, "ground_truth_target_id": 2,
            "failure_class": "candidate_selection_ranking_failure",
            "matched_e016_source_ids": ["s"], "matched_e016_target_ids": ["feasible"],
        }],
    }
    historical = {"transition_ledger": {"recovered_v19_credited_edges": [[1, 2]]}}
    before = deepcopy((graph, record, historical))
    result = audit_sample(record, graph, historical)
    assert result["counts"]["sources_before_final_frame"] == 2
    assert result["counts"]["gate_order_exposed_step_accepted"] == 1
    assert result["loss_overlap_events"] == [{
        "ground_truth_edge": [1, 2], "v25_mechanism": "forward_prediction_ranking_loss",
        "exposed_source_ids": ["s"], "step_local_selects_mapped_target": True,
        "historically_recovered_in_v26a": True,
    }]
    assert (graph, record, historical) == before
    assert [(e.source_id, e.target_id) for e in graph.edges] == [("p", "s")]


def test_archive_identity_failure_stops_before_any_reconstruction(tmp_path):
    damaged = tmp_path / "unverified.zip"
    damaged.write_bytes(b"unverified evidence")
    with pytest.raises(RuntimeError, match="frozen V25 archive mismatch"):
        run_audit(damaged, tmp_path / "does-not-exist.zip")
