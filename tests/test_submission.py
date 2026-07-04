import pytest

from atabey.submission.writer import KAGGLE_SUBMISSION_COLUMNS, graph_to_submission_rows
from atabey.types import Detection, LineageEdge, LineageGraph


def test_submission_rows_match_official_schema_and_map_node_ids():
    graph = LineageGraph(sample_id="sample")
    graph.add_detection(Detection("n1", "sample", 0, 1.2, 2.4, 3.6, 1.0, 2.0, 3.0))
    graph.add_detection(Detection("n2", "sample", 1, 2.0, 3.0, 4.0, 2.0, 3.0, 4.0))
    graph.add_edge(LineageEdge("n1", "n2"))

    rows = graph_to_submission_rows(graph)

    assert rows.columns.tolist() == KAGGLE_SUBMISSION_COLUMNS
    assert rows.shape[0] == 3
    assert rows["id"].tolist() == [0, 1, 2]
    assert rows["dataset"].tolist() == ["sample", "sample", "sample"]
    assert rows.loc[0, "node_id"] == 1
    assert rows.loc[1, "node_id"] == 2
    assert rows.loc[2, "row_type"] == "edge"
    assert rows.loc[2, "source_id"] == 1
    assert rows.loc[2, "target_id"] == 2
    assert rows.loc[2, "node_id"] == -1


def test_submission_writer_rejects_edges_with_missing_nodes():
    graph = LineageGraph(sample_id="sample")
    graph.add_detection(Detection("n1", "sample", 0, 1, 2, 3, 1.0, 2.0, 3.0))
    graph.add_edge(LineageEdge("n1", "missing"))

    with pytest.raises(ValueError, match="absent"):
        graph_to_submission_rows(graph)
