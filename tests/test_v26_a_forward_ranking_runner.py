from collections import Counter
import sys
from pathlib import Path

from atabey.evaluation.official_association_forensics import (
    OfficialAssociationCorrespondence,
    OfficialEdgeCorrespondence,
    OfficialNodeCorrespondence,
)
from atabey.types import LineageEdge, LineageGraph


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_v26_a_forward_ranking_ablation import (
    _reconstruct_frozen_relink,
    build_transition_ledger,
    evaluate_interest_gate,
)


def _correspondence(
    matched_edges: list[tuple[str, str, int, int]],
    unmatched_edges: list[tuple[str, str]],
) -> OfficialAssociationCorrespondence:
    node_ids = sorted(
        {node_id for edge in (*matched_edges, *unmatched_edges) for node_id in edge[:2]}
    )
    nodes = tuple(OfficialNodeCorrespondence(node_id, None) for node_id in node_ids)
    edges = tuple(
        OfficialEdgeCorrespondence(source, target, gt_source, gt_target, True)
        for source, target, gt_source, gt_target in matched_edges
    ) + tuple(
        OfficialEdgeCorrespondence(source, target, None, None, False)
        for source, target in unmatched_edges
    )
    return OfficialAssociationCorrespondence(nodes, edges)


def test_reconstructs_frozen_relink_from_v25_physical_evidence() -> None:
    record = {
        "sample_id": "sample",
        "coordinate_count": 3,
        "visualization": {
            "frames": [
                {
                    "nodes": [
                        {"node_id": "unet:sample:n00000000", "t": 0, "position_um": [1.625, 0.0, 0.0]},
                        {"node_id": "unet:sample:n00000001", "t": 1, "position_um": [1.625, 0.40625, 0.0]},
                    ]
                },
                {
                    "nodes": [
                        {"node_id": "unet:sample:n00000001", "t": 1, "position_um": [1.625, 0.40625, 0.0]},
                        {"node_id": "unet:sample:n00000002", "t": 2, "position_um": [1.625, 0.8125, 0.0]},
                    ]
                },
            ]
        },
        "association_audit": {
            "frames": [
                {"candidates": [{"source_id": "unet:sample:n00000000", "target_id": "unet:sample:n00000001", "prediction_error_um": 0.40625, "accepted": True}]},
                {"candidates": [{"source_id": "unet:sample:n00000001", "target_id": "unet:sample:n00000002", "prediction_error_um": 0.0, "accepted": True}]},
            ]
        },
    }

    graph = _reconstruct_frozen_relink(record)

    assert [(node.z, node.y, node.x) for node in graph.detections] == [
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (1.0, 2.0, 0.0),
    ]
    assert [(edge.source_id, edge.target_id) for edge in graph.edges] == [
        ("unet:sample:n00000000", "unet:sample:n00000001"),
        ("unet:sample:n00000001", "unet:sample:n00000002"),
    ]
    assert graph.edges[0].confidence == 1.0 - 0.40625 / 9.0


def test_transition_ledger_separates_recovery_and_collateral_edges() -> None:
    v19 = _correspondence([("v19-a", "v19-b", 1, 2)], [])
    baseline = _correspondence(
        [("base-a", "base-b", 3, 4)],
        [("base-wrong-a", "base-wrong-b")],
    )
    ablation = _correspondence(
        [("new-a", "new-b", 1, 2)],
        [("new-wrong-a", "new-wrong-b")],
    )
    baseline_graph = LineageGraph(
        "sample",
        edges=[
            LineageEdge("base-a", "base-b"),
            LineageEdge("base-wrong-a", "base-wrong-b"),
        ],
    )
    ablation_graph = LineageGraph(
        "sample",
        edges=[
            LineageEdge("new-a", "new-b"),
            LineageEdge("new-wrong-a", "new-wrong-b"),
        ],
    )

    ledger = build_transition_ledger(
        v19,
        baseline,
        ablation,
        baseline_graph,
        ablation_graph,
    )

    assert ledger["recovered_v19_credited_edges"] == [[1, 2]]
    assert ledger["displaced_v24_3_credited_edges"] == [[3, 4]]
    assert ledger["newly_incorrect_edges"] == [["new-wrong-a", "new-wrong-b"]]
    assert ledger["removed_incorrect_edges"] == [["base-wrong-a", "base-wrong-b"]]
    assert ledger["net_association_delta"] == 0


def test_interest_gate_requires_recovery_without_net_collateral() -> None:
    sample = {
        "transition_ledger": {
            "net_association_delta": 45,
            "net_incorrect_edge_delta": -1,
        },
        "official_metric_delta": {"adjusted_edge_jaccard": 0.01},
        "deterministic_replay": True,
    }
    counts = {
        "forward_prediction_ranking_loss": 44,
        "newly_incorrect_edges": 10,
    }
    gate = {
        "minimum_forward_ranking_recoveries": 44,
        "require_positive_net_association_delta": True,
        "maximum_net_incorrect_edge_delta": 0,
        "maximum_new_incorrect_edges_per_forward_recovery": 0.25,
        "maximum_per_sample_adjusted_edge_jaccard_regression": 0.10,
        "require_deterministic_replay": True,
    }

    result = evaluate_interest_gate([sample], Counter(counts), gate)

    assert result["passed"] is True
    assert result["decision"] == "INTERESTING_FOR_PREREGISTERED_INDEPENDENT_FOLLOWUP"
    assert result["production_tuning_authorized"] is False