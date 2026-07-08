from __future__ import annotations

from atabey.tracking.global_window_optimizer import (
    GlobalWindowSettings,
    compare_greedy_vs_window_global,
)
from atabey.types import Detection


def _detection(*, node_id: str, t: int, z_um: float, y_um: float, x_um: float) -> Detection:
    return Detection(
        node_id=node_id,
        sample_id="sample",
        t=t,
        z=z_um,
        y=y_um,
        x=x_um,
        z_um=z_um,
        y_um=y_um,
        x_um=x_um,
    )


def test_window_global_prefers_two_step_consistent_target() -> None:
    predecessor = _detection(node_id="p0", t=0, z_um=0.0, y_um=0.0, x_um=0.0)
    source = _detection(node_id="p1", t=1, z_um=0.0, y_um=1.0, x_um=0.0)

    # Greedy nearest target from source is c1_a (distance 1.0), but c1_b has
    # a much better continuation into t+2 under global window scoring.
    c1_a = _detection(node_id="c1_a", t=2, z_um=0.0, y_um=2.0, x_um=0.0)
    c1_b = _detection(node_id="c1_b", t=2, z_um=0.0, y_um=3.0, x_um=0.0)
    c2_good = _detection(node_id="c2_good", t=3, z_um=0.0, y_um=5.0, x_um=0.0)

    decision = compare_greedy_vs_window_global(
        source=source,
        predecessor=predecessor,
        current_candidates=[c1_a, c1_b],
        future_candidates=[c2_good],
        max_link_distance_um=3.0,
        link_strategy="greedy",
        settings=GlobalWindowSettings(
            first_step_prediction_weight=0.2,
            first_step_distance_weight=0.1,
            second_step_prediction_weight=2.0,
            second_step_distance_weight=0.2,
            terminal_without_second_step_penalty=2.5,
        ),
    )

    assert decision.greedy_target_id == "c1_a"
    assert decision.global_target_id == "c1_b"
    assert decision.used_second_step is True


def test_window_global_returns_none_without_t_plus_1_candidate() -> None:
    source = _detection(node_id="s", t=3, z_um=0.0, y_um=0.0, x_um=0.0)

    decision = compare_greedy_vs_window_global(
        source=source,
        predecessor=None,
        current_candidates=[],
        future_candidates=[],
        max_link_distance_um=2.0,
        link_strategy="greedy",
    )

    assert decision.greedy_target_id is None
    assert decision.global_target_id is None
    assert decision.global_total_cost is None


def test_window_global_matches_greedy_in_simple_case() -> None:
    predecessor = _detection(node_id="p0", t=0, z_um=0.0, y_um=0.0, x_um=0.0)
    source = _detection(node_id="p1", t=1, z_um=0.0, y_um=1.0, x_um=0.0)
    candidate = _detection(node_id="c1", t=2, z_um=0.0, y_um=2.0, x_um=0.0)

    decision = compare_greedy_vs_window_global(
        source=source,
        predecessor=predecessor,
        current_candidates=[candidate],
        future_candidates=[],
        max_link_distance_um=3.0,
        link_strategy="greedy",
    )

    assert decision.greedy_target_id == "c1"
    assert decision.global_target_id == "c1"
