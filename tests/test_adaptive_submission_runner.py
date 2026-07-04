from pathlib import Path

from scripts.run_adaptive_submission import SampleRunRecord, discover_zarr_samples


class FakePath:
    def __init__(self, name, is_dir=True):
        self.name = name
        self._is_dir = is_dir

    def is_dir(self):
        return self._is_dir


def test_discover_zarr_samples_returns_sorted_directories(monkeypatch):
    fake_paths = [
        FakePath("b.zarr"),
        FakePath("a.zarr"),
        FakePath("not_zarr"),
        FakePath("c.zarr", is_dir=False),
    ]

    monkeypatch.setattr(Path, "iterdir", lambda self: iter(fake_paths))

    samples = discover_zarr_samples("unused")

    assert [path.name for path in samples] == ["a.zarr", "b.zarr"]


def test_sample_run_record_keeps_submission_audit_fields():
    record = SampleRunRecord(
        sample_id="demo",
        sample_path=str(Path("demo.zarr")),
        elapsed_seconds=1.2,
        predicted_nodes=3,
        predicted_edges=2,
        detector="components",
        threshold=0.65,
        min_volume=2,
        peak_min_distance_voxels=(1, 5, 5),
        link_strategy="greedy",
        max_link_distance_um=7.0,
        median_largest_component_voxels=100.0,
        median_foreground_fraction=0.01,
        reason="test",
    )

    assert record.sample_id == "demo"
    assert record.predicted_nodes == 3
    assert record.peak_min_distance_voxels == (1, 5, 5)
