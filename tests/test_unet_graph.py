import pytest

from atabey.tracking.unet_graph import (
    detections_from_predictor_coordinates,
    graph_signature,
    native_graph_from_predictor_output,
    relink_predictor_detections,
)


COORDINATES = [
    [0, 1, 4, 8],
    [0, 2, 20, 20],
    [1, 1, 5, 9],
    [1, 2, 21, 21],
]


def test_predictor_coordinates_are_scaled_once_in_physical_units():
    detections = detections_from_predictor_coordinates("sample", COORDINATES)
    assert detections[0].node_id == "unet:sample:n00000000"
    assert detections[0].position_um == pytest.approx((1.625, 1.625, 3.25))
    assert detections[2].position_um == pytest.approx(
        (1.625, 2.03125, 3.65625)
    )


def test_native_graph_preserves_predictor_edge_identity_and_confidence():
    graph = native_graph_from_predictor_output(
        "sample",
        COORDINATES,
        [(0, 2, 0.9, 0.6), (1, 3, 0.8, 0.6)],
    )
    assert len(graph.detections) == 4
    assert [
        (edge.source_id, edge.target_id, edge.confidence)
        for edge in graph.edges
    ] == [
        ("unet:sample:n00000000", "unet:sample:n00000002", 0.9),
        ("unet:sample:n00000001", "unet:sample:n00000003", 0.8),
    ]


def test_atabey_relink_uses_same_detections_without_native_edges():
    graph = relink_predictor_detections("sample", COORDINATES)
    assert len(graph.detections) == 4
    assert {
        (edge.source_id, edge.target_id) for edge in graph.edges
    } == {
        ("unet:sample:n00000000", "unet:sample:n00000002"),
        ("unet:sample:n00000001", "unet:sample:n00000003"),
    }
    assert all(edge.relation == "continuation" for edge in graph.edges)


def test_both_graph_conversions_are_deterministic():
    native_first = native_graph_from_predictor_output(
        "sample", COORDINATES, [(0, 2, 0.9, 0.6)]
    )
    native_second = native_graph_from_predictor_output(
        "sample", COORDINATES, [(0, 2, 0.9, 0.6)]
    )
    relink_first = relink_predictor_detections("sample", COORDINATES)
    relink_second = relink_predictor_detections("sample", COORDINATES)
    assert graph_signature(native_first) == graph_signature(native_second)
    assert graph_signature(relink_first) == graph_signature(relink_second)


@pytest.mark.parametrize(
    "coordinates",
    [
        [[0, 1, 2]],
        [[0, 1, 2, float("nan")]],
        [[1, 1, 2, 3], [0, 1, 2, 3]],
        [[0.5, 1, 2, 3]],
        [[0, -1, 2, 3]],
    ],
)
def test_invalid_predictor_coordinates_fail_closed(coordinates):
    with pytest.raises(ValueError):
        detections_from_predictor_coordinates("sample", coordinates)


@pytest.mark.parametrize(
    "edge",
    [
        (-1, 2, 0.9, 1.0),
        (0, 99, 0.9, 1.0),
        (0, 1, 0.9, 1.0),
        (0, 2, 1.1, 1.0),
        (0, 2, 0.9, -1.0),
    ],
)
def test_invalid_native_edges_fail_closed(edge):
    with pytest.raises(ValueError):
        native_graph_from_predictor_output("sample", COORDINATES, [edge])


def test_duplicate_native_edges_fail_closed():
    with pytest.raises(ValueError, match="duplicates"):
        native_graph_from_predictor_output(
            "sample",
            COORDINATES,
            [(0, 2, 0.9, 1.0), (0, 2, 0.8, 1.0)],
        )
