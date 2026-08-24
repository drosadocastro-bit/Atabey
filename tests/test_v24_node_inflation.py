import csv
import io

import pytest

from scripts.audit_v24_node_inflation import analyze_rows


def _rows() -> list[dict[str, str]]:
    content = io.StringIO(
        "sample_id,family,v19_reference_detector,"
        "v19_frozen_reference_predicted_nodes,"
        "v19_frozen_reference_adjusted_edge_jaccard,"
        "e016_atabey_relink_predicted_nodes,"
        "e016_atabey_relink_adjusted_edge_jaccard\n"
        "a,44b6,components,100,0.50,100,0.60\n"
        "b,44b6,cfar_sidelobe,100,0.50,130,0.40\n"
        "c,6bba,components,100,0.50,150,0.70\n"
    )
    return list(csv.DictReader(content))


def test_analyze_rows_stratifies_inflation_and_score_outcome():
    report = analyze_rows(_rows())

    assert report["sample_count"] == 3
    assert report["overall"]["median_node_ratio"] == pytest.approx(1.30)
    assert report["overall"]["inflated_samples"] == 2
    assert report["by_family"]["44b6"]["sample_count"] == 2
    assert report["by_route"]["cfar_sidelobe"]["regressed_samples"] == 1
    assert report["by_inflation_status"]["above_ceiling"]["sample_count"] == 2
    assert report["by_inflation_status"]["within_ceiling"]["improved_samples"] == 1


def test_analyze_rows_rejects_missing_numeric_fields():
    rows = _rows()
    del rows[0]["e016_atabey_relink_predicted_nodes"]

    with pytest.raises(ValueError, match="e016_atabey_relink_predicted_nodes"):
        analyze_rows(rows)