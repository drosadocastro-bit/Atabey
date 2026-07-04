import numpy as np

from atabey.diagnostics.intensity import summarize_annotation_intensity
from atabey.io.geff_reader import GroundTruthNode, SparseGroundTruthGraph


class FakeArray:
    shape = (2, 3, 4, 4)

    def __init__(self):
        frame0 = np.zeros((3, 4, 4), dtype=np.uint16)
        frame0[1, 2, 2] = 100
        frame1 = np.ones((3, 4, 4), dtype=np.uint16) * 10
        frame1[1, 1, 1] = 40
        self.frames = [frame0, frame1]

    def __getitem__(self, index):
        return self.frames[index]


def node(node_id, t, z, y, x):
    return GroundTruthNode(
        node_id=node_id,
        t=t,
        z=z,
        y=y,
        x=x,
        z_um=float(z),
        y_um=float(y),
        x_um=float(x),
    )


def test_summarize_annotation_intensity_reads_only_annotated_timepoints(monkeypatch):
    calls = []
    fake = FakeArray()

    def fake_open_competition_array(path):
        return fake

    def fake_read_timepoint(array, t):
        calls.append(t)
        return array[t]

    monkeypatch.setattr("atabey.diagnostics.intensity.open_competition_array", fake_open_competition_array)
    monkeypatch.setattr("atabey.diagnostics.intensity.read_timepoint", fake_read_timepoint)
    gt = SparseGroundTruthGraph(
        sample_id="demo",
        nodes=[node(1, 0, 1, 2, 2), node(2, 1, 1, 1, 1)],
        edges=[],
        estimated_number_of_nodes=None,
    )

    report = summarize_annotation_intensity("demo.zarr", gt, threshold=0.65, local_radius=1)

    assert calls == [0, 1]
    assert report.sample_id == "demo"
    assert report.annotated_nodes == 2
    assert report.annotated_timepoints == 2
    assert len(report.timepoint_stats) == 2
    assert report.centroid_summary.count == 2
    assert report.centroid_summary.fraction_centroid_at_threshold == 1.0
    assert report.centroid_summary.fraction_local_max_at_threshold == 1.0
    assert "failure-analysis evidence" in report.note
