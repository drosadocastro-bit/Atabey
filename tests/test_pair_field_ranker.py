from pathlib import Path

import numpy as np
import pytest

from atabey.tracking.pair_field_ranker import (
    LockedPairFieldData,
    aggregate_event_metrics,
    assemble_action_field,
    build_pair_field_ranker,
    fit_pairwise_logistic,
    event_ranking_rows,
    geometry_features,
    model_parameter_count,
    pair_mask_from_sparse,
    selected_preference_pairs,
    xy_d4,
)


def _action(action_id, event_id, sample_id, label, fold=1):
    return {
        "action_id": action_id,
        "event_id": event_id,
        "sample_id": sample_id,
        "family": "44b6" if sample_id.startswith("a") else "6bba",
        "fold": fold,
        "official_label": label,
        "selected_for_training": True,
        "parent_cache_key": "parent",
        "child_1_relative_um": [1.0, 0.0, 0.0],
        "child_2_relative_um": [-1.0, 0.0, 0.0],
        "daughter_pair_sparse_splat": [
            {"index_zyx": [17, 16, 16], "weight": 1.0},
            {"index_zyx": [15, 16, 16], "weight": 1.0},
        ],
    }


def _data(actions):
    parent = np.zeros((1, 4, 33, 33, 33), dtype=np.float32)
    parent[0, 0] = 0.25
    parent[0, 1] = 0.75
    parent[0, 2, 16, 16, 16] = 1.0
    parent[0, 3] = 1.0
    return LockedPairFieldData(
        root=Path("."),
        actions=tuple(actions),
        events=(),
        parents=({"cache_key": "parent"},),
        parent_tensors=parent,
        parent_index={"parent": 0},
    )


def test_frozen_model_has_exact_parameter_count_and_output_shape():
    import torch

    model = build_pair_field_ranker()
    assert model_parameter_count(model) == 20145
    assert model(torch.zeros((2, 5, 33, 33, 33))).shape == (2,)


def test_action_assembly_keeps_pair_mass_and_control_boundaries():
    action = _action("tp", "event", "a-sample", "official_tp")
    data = _data([action])
    main = assemble_action_field(data, action)
    masked = assemble_action_field(data, action, image_mode="mask_only")
    static = assemble_action_field(data, action, image_mode="static_image")

    assert main.shape == (5, 33, 33, 33)
    assert main[3].sum() == pytest.approx(2.0)
    assert np.all(masked[:2] == 0.0)
    assert np.array_equal(static[0], static[1])
    assert np.array_equal(main[2:], masked[2:])


def test_xy_d4_is_deterministic_and_preserves_channel_mass():
    field = np.arange(5 * 3 * 4 * 4, dtype=np.float32).reshape(5, 3, 4, 4)
    hashes = {xy_d4(field, transform).tobytes() for transform in range(8)}
    assert len(hashes) == 8
    for transform in range(8):
        assert xy_d4(field, transform).sum() == field.sum()


def test_pair_weights_are_equal_by_sample_then_event():
    actions = [
        _action("a1-tp", "a1", "a-sample", "official_tp"),
        _action("a1-fp", "a1", "a-sample", "official_fp"),
        _action("a2-tp", "a2", "a-sample", "official_tp"),
        _action("a2-fp", "a2", "a-sample", "official_fp"),
        _action("b1-tp", "b1", "b-sample", "official_tp"),
        _action("b1-fp1", "b1", "b-sample", "official_fp"),
        _action("b1-fp2", "b1", "b-sample", "official_fp"),
    ]
    pairs, weights = selected_preference_pairs(actions, (1,))
    sample_mass = {"a-sample": 0.0, "b-sample": 0.0}
    event_mass = {"a1": 0.0, "a2": 0.0, "b1": 0.0}
    for (positive, _), weight in zip(pairs, weights):
        sample_mass[actions[positive]["sample_id"]] += weight
        event_mass[actions[positive]["event_id"]] += weight
    assert sample_mass == pytest.approx({"a-sample": 0.5, "b-sample": 0.5})
    assert event_mass == pytest.approx({"a1": 0.25, "a2": 0.25, "b1": 0.5})


def test_pessimistic_ties_count_equal_scores_ahead():
    actions = [
        _action("tp", "event", "a-sample", "official_tp"),
        _action("fp1", "event", "a-sample", "official_fp"),
        _action("fp2", "event", "a-sample", "official_fp"),
    ]
    rows = event_ranking_rows(actions, [1.0, 1.0, 0.0])
    assert rows[0]["best_tp_rank"] == 2
    assert rows[0]["pairwise_accuracy"] == pytest.approx(0.5)
    assert aggregate_event_metrics(rows)["mrr"] == pytest.approx(0.5)


def test_geometry_features_are_swap_invariant():
    action = _action("tp", "event", "a-sample", "official_tp")
    first = geometry_features(action)
    action["child_1_relative_um"], action["child_2_relative_um"] = (
        action["child_2_relative_um"],
        action["child_1_relative_um"],
    )
    assert np.array_equal(first, geometry_features(action))
    assert pair_mask_from_sparse(action["daughter_pair_sparse_splat"]).sum() == pytest.approx(2.0)


def test_v23_pairwise_logistic_is_self_contained_and_learns_preference():
    differences = np.asarray(
        ([1.0, 0.0], [2.0, 0.0], [1.0, 1.0]), dtype=np.float64
    )
    fit = fit_pairwise_logistic(
        differences,
        np.ones(len(differences), dtype=np.float64),
        c=10.0,
    )
    assert fit.converged is True
    assert fit.coefficients[0] > 0.0
