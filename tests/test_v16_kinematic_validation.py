from __future__ import annotations

import json

from scripts.run_v16_kinematic_validation import (
    COHORT_AT_RISK_51,
    COHORT_OUTSIDE_15,
    COHORT_ROUTED_66,
    load_cfar_validation_cohorts,
    summarize_deltas,
)


def test_load_cfar_validation_cohorts_splits_routed_at_risk_and_outside(tmp_path) -> None:
    scan_json = tmp_path / "scan.json"
    scan_json.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "sample_id": "sample_a",
                        "routes_to_cfar": True,
                        "collapse_risk_by_pfa": {"1e-03": True},
                    },
                    {
                        "sample_id": "sample_b",
                        "routes_to_cfar": True,
                        "collapse_risk_by_pfa": {"1e-03": False},
                    },
                    {
                        "sample_id": "sample_c",
                        "routes_to_cfar": False,
                        "collapse_risk_by_pfa": {"1e-03": True},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    cohorts = load_cfar_validation_cohorts(scan_json)

    assert cohorts.routed_cfar_66 == ["sample_a", "sample_b"]
    assert cohorts.at_risk_pfa_1e_03_51 == ["sample_a"]
    assert cohorts.outside_at_risk_15 == ["sample_b"]


def test_summarize_deltas_reports_improved_regressed_and_unchanged_counts() -> None:
    paired_deltas = [
        {"sample_id": "sample_a", "quality_delta": 0.10, "sparse_recall_delta": 0.04, "sparse_edge_recall_delta": 0.06},
        {"sample_id": "sample_b", "quality_delta": -0.05, "sparse_recall_delta": -0.02, "sparse_edge_recall_delta": -0.03},
        {"sample_id": "sample_c", "quality_delta": 0.0, "sparse_recall_delta": 0.0, "sparse_edge_recall_delta": 0.0},
    ]

    summary = summarize_deltas(
        cohort_name=COHORT_ROUTED_66,
        paired_deltas=paired_deltas,
        sample_ids={"sample_a", "sample_b", "sample_c"},
    )

    assert summary.cohort == COHORT_ROUTED_66
    assert summary.samples == 3
    assert round(summary.mean_quality_delta, 6) == 0.016667
    assert round(summary.mean_sparse_recall_delta, 6) == 0.006667
    assert round(summary.mean_sparse_edge_recall_delta, 6) == 0.01
    assert summary.improved == 1
    assert summary.regressed == 1
    assert summary.unchanged == 1


def test_cohort_name_constants_match_validation_report_contract() -> None:
    assert COHORT_ROUTED_66 == "routed_cfar_66"
    assert COHORT_AT_RISK_51 == "at_risk_pfa_1e_03_51"
    assert COHORT_OUTSIDE_15 == "outside_at_risk_15"