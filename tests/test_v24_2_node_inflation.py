from scripts.audit_v24_2_node_inflation import analyze_rows


def _row(**overrides):
    row = {
        "sample_id": "6bba_case",
        "family": "6bba",
        "v19_reference_detector": "components",
        "v19_frozen_reference_predicted_nodes": "100",
        "e016_atabey_relink_predicted_nodes": "140",
        "e016_atabey_relink_v24_2_shadow_predicted_nodes": "120",
        "e016_atabey_relink_v24_2_shadow_shadow_removed_nodes": "20",
        "e016_atabey_relink_v24_2_shadow_shadow_edge_set_preserved": "True",
    }
    row.update(overrides)
    return row


def test_v24_2_decomposition_records_removed_and_residual_nodes():
    report = analyze_rows([_row()])

    sample = report["samples"][0]
    assert sample["removed_nodes"] == 20
    assert sample["remaining_nodes_after_prune"] == 120
    assert sample["shadow_node_ratio"] == 1.2
    assert report["overall"]["total_removed_nodes"] == 20
    assert report["overall"]["inflated_samples"] == 0
    assert report["edge_sets_preserved_for_all"] is True


def test_v24_2_decomposition_does_not_claim_unavailable_node_semantics():
    report = analyze_rows([_row(e016_atabey_relink_v24_2_shadow_predicted_nodes="130")])

    assert "not classifiable" in report["interpretation"]["remaining_nodes"]
    assert report["overall"]["inflated_samples"] == 1