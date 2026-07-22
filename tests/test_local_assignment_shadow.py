from __future__ import annotations

from atabey.tracking.local_assignment_shadow import PairHypothesis, rank_local_pair_hypotheses
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(node_id: str, t: int, x: float, y: float = 0.0) -> Detection:
    return Detection(node_id, "sample", t, 0.0, y, x, 0.0, y, x)


def test_local_assignment_demotes_pair_that_steals_a_competitor_target_without_mutation():
    focal = _d("focal", 0, 0.0)
    competitor = _d("competitor", 0, 10.0)
    good_1 = _d("good_1", 1, 1.0, 2.0)
    good_2 = _d("good_2", 1, 1.0, -2.0)
    stolen = _d("stolen", 1, 11.0)
    graph = LineageGraph("sample", [focal, competitor, good_1, good_2, stolen], [LineageEdge("competitor", "stolen")])
    before = list(graph.edges)

    results = rank_local_pair_hypotheses(
        graph,
        "focal",
        [PairHypothesis("good_1", "stolen", 0.9, 1), PairHypothesis("good_1", "good_2", 0.8, 2)],
    )

    assert next(row for row in results if row.child_2_id == "good_2").local_rank == 1
    stolen_result = next(row for row in results if row.child_2_id == "stolen")
    assert stolen_result.displaced_parents == 1
    assert graph.edges == before


def test_no_competitor_preserves_base_score_order():
    graph = LineageGraph("sample", [_d("focal", 0, 0.0), _d("a", 1, 1.0), _d("b", 1, 2.0), _d("c", 1, 3.0)])
    results = rank_local_pair_hypotheses(
        graph,
        "focal",
        [PairHypothesis("a", "b", 0.7, 1), PairHypothesis("a", "c", 0.6, 2)],
    )
    assert [(row.child_1_id, row.child_2_id, row.local_rank) for row in results] == [("a", "b", 1), ("a", "c", 2)]


def test_competitor_can_reassign_to_alternative_with_measured_cost_increase():
    focal = _d("focal", 0, 0.0)
    competitor = _d("competitor", 0, 10.0)
    disputed = _d("disputed", 1, 11.0)
    alternative = _d("alternative", 1, 13.0)
    other = _d("other", 1, 1.0)
    graph = LineageGraph("sample", [focal, competitor, disputed, alternative, other], [LineageEdge("competitor", "disputed")])
    result = rank_local_pair_hypotheses(
        graph,
        "focal",
        [PairHypothesis("disputed", "other", 1.0, 1)],
    )[0]
    assert result.displaced_parents == 0
    assert result.assignment_cost_increase_um == 2.0
