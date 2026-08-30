import json
from pathlib import Path

from atabey.types import Detection, LineageEdge, LineageGraph
from scripts.run_v24_7_route_90_shadow import (
    _canonical_text_sha256,
    apply_edge_proposal,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "tests/fixtures/v24_7_route_90_shadow.json"


def test_route_90_contract_is_fixed_and_bounded() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    cohort = contract["cohort"]
    sample_ids = cohort["sample_ids"]
    regressions = cohort["regression_sample_ids"]
    assert cohort["expected_samples"] == 90
    assert len(sample_ids) == len(set(sample_ids)) == 90
    assert sample_ids == sorted(sample_ids)
    assert all(sample_id.startswith("6bba_") for sample_id in sample_ids)
    assert len(regressions) == len(set(regressions)) == 16
    assert set(regressions) < set(sample_ids)
    assert cohort["route"] == {
        "family": "6bba",
        "v19_reference_detector": "components",
        "v19_reference_link_strategy": "greedy",
    }

    shadow = contract["shadow"]
    assert shadow == {
        "max_counterfactual_edges": 64,
        "commitment_horizon_frames": 2,
        "max_ilp_windows": 16,
        "baseline_change_penalty_um": 2.0,
        "minimum_improvement_um": 0.5,
        "max_variables": 512,
        "time_limit_seconds": 5.0,
    }
    assert contract["execution"]["max_timepoints"] is None
    assert contract["boundaries"] == {
        "assignment_enabled": False,
        "selector_enabled": False,
        "production_graph_mutation": False,
        "submission_authorized": False,
        "threshold_tuning": False,
    }


def test_route_90_provenance_hash_is_platform_stable(tmp_path: Path) -> None:
    lf_path = tmp_path / "lf.txt"
    crlf_path = tmp_path / "crlf.txt"
    changed_path = tmp_path / "changed.txt"
    lf_path.write_bytes(b"route\nrecord\n")
    crlf_path.write_bytes(b"route\r\nrecord\r\n")
    changed_path.write_bytes(b"route\nchanged\n")

    assert _canonical_text_sha256(lf_path) == _canonical_text_sha256(crlf_path)
    assert _canonical_text_sha256(lf_path) != _canonical_text_sha256(changed_path)


def test_apply_edge_proposal_returns_new_graph() -> None:
    graph = LineageGraph(sample_id="sample")
    for node_id, frame, x_um in (
        ("a", 0, 0.0),
        ("b", 1, 1.0),
        ("c", 1, 2.0),
    ):
        graph.add_detection(
            Detection(
                node_id=node_id,
                sample_id="sample",
                t=frame,
                z=0.0,
                y=0.0,
                x=x_um,
                z_um=0.0,
                y_um=0.0,
                x_um=x_um,
            )
        )
    graph.add_edge(LineageEdge(source_id="a", target_id="b"))

    proposed = apply_edge_proposal(
        graph,
        removed_edges=(("a", "b"),),
        added_edges=(("a", "c"),),
    )

    assert [(edge.source_id, edge.target_id) for edge in graph.edges] == [("a", "b")]
    assert proposed is not graph
    assert proposed.detections == graph.detections
    assert [(edge.source_id, edge.target_id) for edge in proposed.edges] == [("a", "c")]


def test_apply_edge_proposal_rejects_invalid_edges() -> None:
    graph = LineageGraph(sample_id="sample")

    try:
        apply_edge_proposal(
            graph,
            removed_edges=(("missing", "edge"),),
            added_edges=(),
        )
    except ValueError as error:
        assert "absent baseline edge" in str(error)
    else:
        raise AssertionError("Missing removal must fail closed")