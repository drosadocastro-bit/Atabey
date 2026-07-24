from __future__ import annotations

import json
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "v21_semantic_dataset_split.json"

LOCKED_VALIDATION = {
    "6bba_784a78c9",
    "44b6_996155de",
    "6bba_09961292",
    "6bba_085bf656",
    "44b6_d5e7d891",
    "6bba_c328f2fd",
    "6bba_f20478e9",
    "44b6_341df25f",
    "6bba_12665c0e",
    "6bba_7f87b3d8",
    "44b6_9be80b04",
    "44b6_a21120c2",
    "6bba_e16ffc58",
    "44b6_c8e2a523",
    "6bba_337b1b3a",
    "6bba_b204cac7",
    "6bba_786893ac",
    "6bba_d1acb6ff",
    "6bba_48816121",
    "44b6_e28840c6",
}


def test_preregistered_semantic_splits_are_balanced_and_disjoint():
    manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
    development = manifest["splits"]["development"]
    calibration = manifest["splits"]["calibration"]
    development_ids = {row["sample_id"] for row in development}
    calibration_ids = {row["sample_id"] for row in calibration}

    assert len(development) == 27
    assert len(calibration) == 27
    assert sum(row["gt_divisions"] for row in development) == 46
    assert sum(row["gt_divisions"] for row in calibration) == 47
    assert development_ids.isdisjoint(calibration_ids)
    assert (development_ids | calibration_ids).isdisjoint(LOCKED_VALIDATION)
    assert len(development_ids | calibration_ids) == 54


def test_each_preregistered_split_contains_both_sample_families():
    manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))

    for rows in manifest["splits"].values():
        family_counts = {
            family: sum(row["family"] == family for row in rows)
            for family in ("44b6", "6bba")
        }
        assert family_counts == {"44b6": 5, "6bba": 22}
