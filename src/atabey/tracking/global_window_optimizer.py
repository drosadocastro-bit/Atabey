from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from atabey.tracking.nearest_neighbor import LinkStrategy, link_adjacent_timepoints
from atabey.types import Detection


@dataclass(frozen=True)
class GlobalWindowSettings:
    first_step_prediction_weight: float = 1.0
    first_step_distance_weight: float = 0.4
    second_step_prediction_weight: float = 1.0
    second_step_distance_weight: float = 0.3
    terminal_without_second_step_penalty: float = 1.2
    weight_scale: int = 1000


@dataclass(frozen=True)
class GlobalWindowDecision:
    source_id: str
    greedy_target_id: str | None
    global_target_id: str | None
    greedy_distance_um: float | None
    global_total_cost: float | None
    used_second_step: bool
    candidate_count_t_plus_1: int
    candidate_count_t_plus_2: int


def compare_greedy_vs_window_global(
    *,
    source: Detection,
    predecessor: Detection | None,
    current_candidates: list[Detection],
    future_candidates: list[Detection],
    max_link_distance_um: float,
    link_strategy: LinkStrategy = "motion_mutual",
    settings: GlobalWindowSettings = GlobalWindowSettings(),
) -> GlobalWindowDecision:
    greedy_target_id, greedy_distance_um = _greedy_choice(
        source=source,
        predecessor=predecessor,
        current_candidates=current_candidates,
        max_link_distance_um=max_link_distance_um,
        link_strategy=link_strategy,
    )

    global_target_id, global_total_cost, used_second_step = _window_global_choice(
        source=source,
        predecessor=predecessor,
        current_candidates=current_candidates,
        future_candidates=future_candidates,
        max_link_distance_um=max_link_distance_um,
        settings=settings,
    )

    return GlobalWindowDecision(
        source_id=source.node_id,
        greedy_target_id=greedy_target_id,
        global_target_id=global_target_id,
        greedy_distance_um=greedy_distance_um,
        global_total_cost=global_total_cost,
        used_second_step=used_second_step,
        candidate_count_t_plus_1=len(current_candidates),
        candidate_count_t_plus_2=len(future_candidates),
    )


def _greedy_choice(
    *,
    source: Detection,
    predecessor: Detection | None,
    current_candidates: list[Detection],
    max_link_distance_um: float,
    link_strategy: LinkStrategy,
) -> tuple[str | None, float | None]:
    edges = link_adjacent_timepoints(
        [source],
        current_candidates,
        max_link_distance_um,
        strategy=link_strategy,
        predecessor_by_node_id=({source.node_id: predecessor} if predecessor is not None else {}),
    )
    if not edges:
        return None, None

    target_id = str(edges[0].target_id)
    target = next((candidate for candidate in current_candidates if candidate.node_id == target_id), None)
    if target is None:
        return target_id, None
    return target_id, _distance_um(source, target)


def _window_global_choice(
    *,
    source: Detection,
    predecessor: Detection | None,
    current_candidates: list[Detection],
    future_candidates: list[Detection],
    max_link_distance_um: float,
    settings: GlobalWindowSettings,
) -> tuple[str | None, float | None, bool]:
    filtered_t1 = [
        candidate
        for candidate in current_candidates
        if _distance_um(source, candidate) <= float(max_link_distance_um)
    ]
    if not filtered_t1:
        return None, None, False

    transitions_t2: dict[str, list[Detection]] = {}
    filtered_t2_ids: set[str] = set()
    for candidate_t1 in filtered_t1:
        neighbors = [
            candidate_t2
            for candidate_t2 in future_candidates
            if _distance_um(candidate_t1, candidate_t2) <= float(max_link_distance_um)
        ]
        transitions_t2[candidate_t1.node_id] = neighbors
        filtered_t2_ids.update(candidate.node_id for candidate in neighbors)

    filtered_t2 = [candidate for candidate in future_candidates if candidate.node_id in filtered_t2_ids]

    try:
        return _solve_min_cost_flow(
            source=source,
            predecessor=predecessor,
            candidates_t1=filtered_t1,
            transitions_t2=transitions_t2,
            settings=settings,
        )
    except Exception:
        return _solve_window_dynamic_program(
            source=source,
            predecessor=predecessor,
            candidates_t1=filtered_t1,
            transitions_t2=transitions_t2,
            settings=settings,
        )


def _solve_min_cost_flow(
    *,
    source: Detection,
    predecessor: Detection | None,
    candidates_t1: list[Detection],
    transitions_t2: dict[str, list[Detection]],
    settings: GlobalWindowSettings,
) -> tuple[str | None, float | None, bool]:
    import networkx as nx

    graph = nx.DiGraph()
    graph.add_node("S", demand=-1)
    graph.add_node("T", demand=1)

    t2_node_ids: set[str] = set()
    for candidate_t1 in candidates_t1:
        node_t1 = _node_name_t1(candidate_t1)
        graph.add_node(node_t1, demand=0)
        start_cost = _first_step_cost(
            source=source,
            predecessor=predecessor,
            target=candidate_t1,
            settings=settings,
        )
        graph.add_edge(
            "S",
            node_t1,
            capacity=1,
            weight=int(round(start_cost * float(settings.weight_scale))),
        )

        terminal_weight = int(round(float(settings.terminal_without_second_step_penalty) * float(settings.weight_scale)))
        graph.add_edge(node_t1, "T", capacity=1, weight=terminal_weight)

        for candidate_t2 in transitions_t2.get(candidate_t1.node_id, []):
            node_t2 = _node_name_t2(candidate_t2)
            if node_t2 not in graph:
                graph.add_node(node_t2, demand=0)
                graph.add_edge(node_t2, "T", capacity=1, weight=0)
            t2_node_ids.add(node_t2)

            second_cost = _second_step_cost(
                source=source,
                pivot=candidate_t1,
                target=candidate_t2,
                settings=settings,
            )
            graph.add_edge(
                node_t1,
                node_t2,
                capacity=1,
                weight=int(round(second_cost * float(settings.weight_scale))),
            )

    flow = nx.min_cost_flow(graph)

    chosen_t1_node = None
    for node_t1, flow_value in flow.get("S", {}).items():
        if int(flow_value) > 0:
            chosen_t1_node = node_t1
            break
    if chosen_t1_node is None:
        return None, None, False

    chosen_t1_id = chosen_t1_node[len("T1|") :]
    used_second_step = any(
        int(flow_value) > 0 and str(node).startswith("T2|")
        for node, flow_value in flow.get(chosen_t1_node, {}).items()
    )

    total_cost = float(nx.cost_of_flow(graph, flow)) / float(settings.weight_scale)
    return chosen_t1_id, total_cost, bool(used_second_step)


def _solve_window_dynamic_program(
    *,
    source: Detection,
    predecessor: Detection | None,
    candidates_t1: list[Detection],
    transitions_t2: dict[str, list[Detection]],
    settings: GlobalWindowSettings,
) -> tuple[str | None, float | None, bool]:
    best_target_id: str | None = None
    best_cost = math.inf
    best_uses_second = False

    for candidate_t1 in candidates_t1:
        base_cost = _first_step_cost(
            source=source,
            predecessor=predecessor,
            target=candidate_t1,
            settings=settings,
        )
        best_local = base_cost + float(settings.terminal_without_second_step_penalty)
        uses_second = False
        for candidate_t2 in transitions_t2.get(candidate_t1.node_id, []):
            second_cost = _second_step_cost(
                source=source,
                pivot=candidate_t1,
                target=candidate_t2,
                settings=settings,
            )
            candidate_cost = base_cost + second_cost
            if candidate_cost < best_local:
                best_local = candidate_cost
                uses_second = True

        if best_local < best_cost:
            best_cost = best_local
            best_target_id = candidate_t1.node_id
            best_uses_second = uses_second

    if best_target_id is None or not math.isfinite(best_cost):
        return None, None, False
    return best_target_id, best_cost, best_uses_second


def _first_step_cost(
    *,
    source: Detection,
    predecessor: Detection | None,
    target: Detection,
    settings: GlobalWindowSettings,
) -> float:
    predicted = _predicted_position(source, predecessor)
    prediction_error = float(np.linalg.norm(np.array(target.position_um, dtype=float) - predicted))
    direct_distance = _distance_um(source, target)
    return (
        float(settings.first_step_prediction_weight) * prediction_error
        + float(settings.first_step_distance_weight) * direct_distance
    )


def _second_step_cost(
    *,
    source: Detection,
    pivot: Detection,
    target: Detection,
    settings: GlobalWindowSettings,
) -> float:
    predicted = _predicted_from_pivot(source=source, pivot=pivot)
    prediction_error = float(np.linalg.norm(np.array(target.position_um, dtype=float) - predicted))
    direct_distance = _distance_um(pivot, target)
    return (
        float(settings.second_step_prediction_weight) * prediction_error
        + float(settings.second_step_distance_weight) * direct_distance
    )


def _predicted_position(source: Detection, predecessor: Detection | None) -> np.ndarray:
    source_position = np.array(source.position_um, dtype=float)
    if predecessor is None:
        return source_position
    velocity = source_position - np.array(predecessor.position_um, dtype=float)
    return source_position + velocity


def _predicted_from_pivot(*, source: Detection, pivot: Detection) -> np.ndarray:
    source_position = np.array(source.position_um, dtype=float)
    pivot_position = np.array(pivot.position_um, dtype=float)
    velocity = pivot_position - source_position
    return pivot_position + velocity


def _distance_um(left: Detection, right: Detection) -> float:
    return float(np.linalg.norm(np.array(left.position_um, dtype=float) - np.array(right.position_um, dtype=float)))


def _node_name_t1(detection: Detection) -> str:
    return f"T1|{detection.node_id}"


def _node_name_t2(detection: Detection) -> str:
    return f"T2|{detection.node_id}"
