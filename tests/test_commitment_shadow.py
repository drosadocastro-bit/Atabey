from atabey.tracking.commitment_shadow import audit_motion_mutual_commitment
from atabey.tracking.unet_graph import graph_signature, relink_predictor_detections


def test_predecessor_ablation_exposes_downstream_assignment_lock_in():
    coordinates = [
        [0, 0.0, 0.0, 0.0],
        [1, 0.0, 1.0, 0.0],
        [2, 0.0, 2.0, 0.0],
        [2, 0.0, 1.1, 0.0],
    ]
    graph = relink_predictor_detections("sample", coordinates)
    before = graph_signature(graph)

    summary = audit_motion_mutual_commitment(
        graph,
        horizon_frames=1,
        max_counterfactual_edges=8,
    )

    assert graph_signature(graph) == before
    assert summary.eligible_edge_count == 1
    assert summary.counterfactual_edge_count == 1
    assert summary.commitment_sensitive_edge_count == 1
    record = summary.records[0]
    assert record.source_id == "unet:sample:n00000000"
    assert record.target_id == "unet:sample:n00000001"
    assert record.changed_assignment_count == 1
    assert record.reconverged is False


def test_counterfactual_budget_is_deterministic_and_bounded():
    coordinates = [
        [0, 0.0, 0.0, 0.0],
        [0, 0.0, 10.0, 0.0],
        [1, 0.0, 1.0, 0.0],
        [1, 0.0, 11.0, 0.0],
        [2, 0.0, 2.0, 0.0],
        [2, 0.0, 12.0, 0.0],
    ]
    graph = relink_predictor_detections("sample", coordinates)

    first = audit_motion_mutual_commitment(graph, max_counterfactual_edges=1)
    second = audit_motion_mutual_commitment(graph, max_counterfactual_edges=1)

    assert first == second
    assert first.eligible_edge_count == 2
    assert first.counterfactual_edge_count == 1
    assert len(first.records) == 1