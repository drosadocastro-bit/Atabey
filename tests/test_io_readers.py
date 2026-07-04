from pathlib import Path

from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint, sample_id_from_zarr_path


DATA_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = DATA_ROOT / "train" / "44b6_0113de3b.zarr"
LABELS = DATA_ROOT / "train" / "44b6_0113de3b.geff"


def test_sample_id_from_zarr_path_uses_dataset_name():
    assert sample_id_from_zarr_path(SAMPLE) == "44b6_0113de3b"


def test_open_competition_array_reads_one_timepoint():
    array = open_competition_array(SAMPLE)

    assert array.shape == (100, 64, 256, 256)
    assert str(array.dtype) == "uint16"
    timepoint = read_timepoint(array, 0)
    assert timepoint.shape == (64, 256, 256)


def test_read_geff_graph_extracts_sparse_nodes_edges_and_estimate():
    graph = read_geff_graph(LABELS)

    assert graph.sample_id == "44b6_0113de3b"
    assert len(graph.nodes) == 52
    assert len(graph.edges) == 50
    assert graph.estimated_number_of_nodes == 25755
    assert graph.nodes[0].t == 0
    assert graph.nodes[0].z == 63
    assert graph.edges[0] == (11000000075, 12000000075)
