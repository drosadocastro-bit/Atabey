from __future__ import annotations

from atabey.tracking.safe_division_shadow import (
    SafeDivisionShadowConfig,
    compute_safe_division_shadow,
    project_safe_division_shadow,
)
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(node_id: str, t: int, x: float, y: float = 0.0) -> Detection:
    return Detection(node_id, "sample", t, 0.0, y, x, 0.0, y, x)


def _signature(graph: LineageGraph):
    return tuple(graph.detections), tuple(graph.edges)


def test_safe_division_shadow_selects_unowned_sister_without_mutation():
    graph = LineageGraph(
        "sample",
        [_d("p", 0, 0.0), _d("a", 1, 2.0), _d("b", 1, 3.0)],
        [LineageEdge("p", "a")],
    )
    before = _signature(graph)

    shadow = compute_safe_division_shadow(graph)

    assert _signature(graph) == before
    assert shadow.proposal_count == 1
    assert shadow.selected_count == 1
    candidate = shadow.candidates[0]
    assert candidate.selected is True
    assert candidate.selection_reason == "selected"
    assert candidate.parent_candidate_distance_um == 3.0
    assert candidate.existing_child_distance_um == 2.0
    assert candidate.sister_distance_um == 1.0
    assert candidate.score == 3.15

    projected = project_safe_division_shadow(graph, shadow)
    assert _signature(graph) == before
    assert len(projected.edges) == 2
    assert projected.edges[-1] == LineageEdge("p", "b", relation="division")


def test_safe_division_shadow_excludes_already_owned_candidate():
    graph = LineageGraph(
        "sample",
        [
            _d("p", 0, 0.0),
            _d("q", 0, 10.0),
            _d("a", 1, 2.0),
            _d("b", 1, 3.0),
        ],
        [LineageEdge("p", "a"), LineageEdge("q", "b")],
    )

    shadow = compute_safe_division_shadow(graph)

    assert shadow.proposal_count == 0
    assert shadow.selected_count == 0


def test_safe_division_shadow_uses_stable_score_order_for_competing_parents():
    graph = LineageGraph(
        "sample",
        [
            _d("p-near", 0, 0.0),
            _d("p-far", 0, 1.0),
            _d("a-near", 1, -1.0),
            _d("a-far", 1, 2.0),
            _d("candidate", 1, 0.25),
        ],
        [LineageEdge("p-near", "a-near"), LineageEdge("p-far", "a-far")],
    )

    shadow = compute_safe_division_shadow(graph)

    assert shadow.proposal_count == 2
    assert shadow.selected_count == 1
    selected = [row for row in shadow.candidates if row.selected]
    rejected = [row for row in shadow.candidates if not row.selected]
    assert selected[0].parent_id == "p-near"
    assert rejected[0].parent_id == "p-far"
    assert rejected[0].selection_reason == "global_cap_reached"


def test_safe_division_shadow_honors_exact_distance_bounds():
    graph = LineageGraph(
        "sample",
        [
            _d("p", 0, 0.0),
            _d("a", 1, 7.65),
            _d("inside", 1, 4.66),
            _d("outside", 1, 4.661),
        ],
        [LineageEdge("p", "a")],
    )

    shadow = compute_safe_division_shadow(
        graph,
        config=SafeDivisionShadowConfig(sister_max_um=8.5),
    )

    assert [row.candidate_child_id for row in shadow.candidates] == ["inside"]


def test_safe_division_shadow_global_cap_is_deterministic():
    detections = []
    edges = []
    for index in range(2):
        base = float(index * 20)
        detections.extend(
            [
                _d(f"p{index}", index * 2, base),
                _d(f"a{index}", index * 2 + 1, base + 1.0),
                _d(f"b{index}", index * 2 + 1, base + 2.0),
            ]
        )
        edges.append(LineageEdge(f"p{index}", f"a{index}"))
    graph = LineageGraph("sample", detections, edges)

    shadow = compute_safe_division_shadow(graph)

    assert shadow.global_cap == 1
    assert shadow.proposal_count == 2
    assert shadow.selected_count == 1
    assert [row.selection_reason for row in shadow.candidates] == [
        "selected",
        "global_cap_reached",
    ]


def test_safe_division_shadow_faithfully_allows_multiple_additions_per_parent():
    graph = LineageGraph(
        "sample",
        [
            _d("p", 0, 0.0),
            _d("a", 1, 1.0),
            _d("b", 1, 2.0),
            _d("c", 1, 3.0),
        ],
        [LineageEdge("p", "a")],
    )
    config = SafeDivisionShadowConfig(
        frame_fraction_cap=2.0,
        global_fraction_cap=2.0,
    )

    shadow = compute_safe_division_shadow(graph, config=config)
    projected = project_safe_division_shadow(graph, shadow)

    assert shadow.selected_count == 2
    assert [row.parent_id for row in shadow.candidates if row.selected] == ["p", "p"]
    assert len([edge for edge in projected.edges if edge.source_id == "p"]) == 3
