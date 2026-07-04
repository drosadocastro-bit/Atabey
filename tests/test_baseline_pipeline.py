import numpy as np
from pathlib import Path

from atabey.baseline import build_baseline_graph
from atabey.types import Detection


class FakeArray:
    shape = (2, 3, 5, 5)

    def __init__(self):
        first = np.zeros((3, 5, 5), dtype=np.uint16)
        first[1, 2, 2] = 100
        second = np.zeros((3, 5, 5), dtype=np.uint16)
        second[1, 2, 3] = 100
        self.frames = [first, second]

    def __getitem__(self, index):
        return self.frames[index]


def test_build_baseline_graph_streams_timepoints_and_links(monkeypatch):
    sample = Path("demo.zarr")
    calls = []

    def fake_open_competition_array(path):
        calls.append(path)
        return FakeArray()

    monkeypatch.setattr("atabey.baseline.open_competition_array", fake_open_competition_array)

    graph = build_baseline_graph(
        sample,
        threshold=0.5,
        min_volume=1,
        max_link_distance_um=2.0,
    )

    assert calls == [sample]
    assert graph.sample_id == "demo"
    assert len(graph.detections) == 2
    assert len(graph.edges) == 1
    assert graph.edges[0].source_id == graph.detections[0].node_id
    assert graph.edges[0].target_id == graph.detections[1].node_id


class GapArray:
    shape = (5, 1, 1, 1)

    def __getitem__(self, index):
        return np.zeros((1, 1, 1), dtype=np.uint16)


def test_build_baseline_graph_latent_bridge_recovers_one_frame_gap(monkeypatch):
    sample = Path("demo.zarr")

    def fake_open_competition_array(path):
        return GapArray()

    detections_by_t = {
        0: [Detection("demo:t0:a0", "demo", 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)],
        1: [Detection("demo:t1:a1", "demo", 1, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0)],
        2: [Detection("demo:t2:a2", "demo", 2, 0.0, 0.0, 2.0, 0.0, 0.0, 2.0)],
        3: [],
        4: [Detection("demo:t4:a4", "demo", 4, 0.0, 0.0, 4.0, 0.0, 0.0, 4.0)],
    }

    def fake_components(sample_id, t, volume, threshold, min_volume):
        return detections_by_t[int(t)]

    monkeypatch.setattr("atabey.baseline.open_competition_array", fake_open_competition_array)
    monkeypatch.setattr("atabey.baseline.threshold_connected_components", fake_components)

    graph = build_baseline_graph(
        sample,
        detector="components",
        link_strategy="motion_mutual_latent",
        max_link_distance_um=2.0,
        threshold=0.5,
        min_volume=1,
    )

    assert len(graph.detections) == 4
    assert [(edge.source_id, edge.target_id, edge.relation) for edge in graph.edges] == [
        ("demo:t0:a0", "demo:t1:a1", "continuation"),
        ("demo:t1:a1", "demo:t2:a2", "continuation"),
        ("demo:t2:a2", "demo:t4:a4", "latent_recovery"),
    ]


class LateStartGapArray:
    shape = (4, 1, 1, 1)

    def __getitem__(self, index):
        return np.zeros((1, 1, 1), dtype=np.uint16)


def test_build_baseline_graph_latent_bridge_skips_tracks_without_history(monkeypatch):
    sample = Path("demo.zarr")

    def fake_open_competition_array(path):
        return LateStartGapArray()

    detections_by_t = {
        0: [],
        1: [Detection("demo:t1:new", "demo", 1, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0)],
        2: [],
        3: [Detection("demo:t3:reappear", "demo", 3, 0.0, 0.0, 3.0, 0.0, 0.0, 3.0)],
    }

    def fake_components(sample_id, t, volume, threshold, min_volume):
        return detections_by_t[int(t)]

    monkeypatch.setattr("atabey.baseline.open_competition_array", fake_open_competition_array)
    monkeypatch.setattr("atabey.baseline.threshold_connected_components", fake_components)

    graph = build_baseline_graph(
        sample,
        detector="components",
        link_strategy="motion_mutual_latent",
        max_link_distance_um=2.0,
        threshold=0.5,
        min_volume=1,
    )

    assert len(graph.detections) == 2
    assert graph.edges == []


def test_build_baseline_graph_latent_bridge_requires_track_history(monkeypatch):
    sample = Path("demo.zarr")

    def fake_open_competition_array(path):
        return LateStartGapArray()

    detections_by_t = {
        0: [Detection("demo:t0:start", "demo", 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)],
        1: [Detection("demo:t1:mid", "demo", 1, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0)],
        2: [],
        3: [Detection("demo:t3:back", "demo", 3, 0.0, 0.0, 3.0, 0.0, 0.0, 3.0)],
    }

    def fake_components(sample_id, t, volume, threshold, min_volume):
        return detections_by_t[int(t)]

    monkeypatch.setattr("atabey.baseline.open_competition_array", fake_open_competition_array)
    monkeypatch.setattr("atabey.baseline.threshold_connected_components", fake_components)

    graph = build_baseline_graph(
        sample,
        detector="components",
        link_strategy="motion_mutual_latent",
        max_link_distance_um=2.0,
        threshold=0.5,
        min_volume=1,
    )

    # The track has only one accepted edge before the gap, so it should not enter
    # latent recovery under the minimum track-history gate.
    assert [(edge.source_id, edge.target_id, edge.relation) for edge in graph.edges] == [
        ("demo:t0:start", "demo:t1:mid", "continuation")
    ]
