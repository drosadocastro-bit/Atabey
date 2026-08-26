import hashlib
import json
from pathlib import Path

import pytest

from scripts.run_v24_3_full_199_score_validation import (
    SHARD_COMPLETE,
    discover_paired_samples,
    validate_full_27_authorization,
)
from scripts.merge_v24_3_full_199_score_validation import collect_shard_records


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_text_sha256(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_full_199_contract_pins_authorization_sources_and_boundaries():
    contract = json.loads(
        (ROOT / "tests/fixtures/v24_3_full_199_score_validation.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["population"] == {
        "expected_samples": 199,
        "checkpoint_training_samples": 172,
        "held_out_samples": 27,
        "shard_count": 2,
        "partition": "sorted_sample_ids_stride_by_shard_index",
    }
    assert _normalized_text_sha256(
        ROOT / contract["authorization"]["report_path"]
    ) == contract["authorization"]["report_normalized_sha256"]
    for source in contract["sources"]:
        assert _normalized_text_sha256(ROOT / source["path"]) == source["sha256"]
    assert contract["boundaries"]["independent_generalization_claim"] is False
    assert contract["boundaries"]["submission_authorized"] is False


def test_discover_paired_samples_requires_exact_population(tmp_path):
    for sample_id in ("44b6_a", "6bba_b"):
        (tmp_path / f"{sample_id}.zarr").mkdir()
        (tmp_path / f"{sample_id}.geff").mkdir()

    assert discover_paired_samples(tmp_path, expected_count=2) == ["44b6_a", "6bba_b"]

    (tmp_path / "6bba_unpaired.zarr").mkdir()
    with pytest.raises(RuntimeError, match="paired sample mismatch"):
        discover_paired_samples(tmp_path, expected_count=2)


def test_validate_full_27_authorization_requires_exact_report(tmp_path):
    report = {
        "decision": "GO_TO_FULL_199_SCORE_VALIDATION",
        "evaluation_commit": "frozen-commit",
        "evaluated_arm": "e016_atabey_relink_v24_3_short_fragment_shadow",
        "determinism_verified": True,
        "authorization": {
            "full_199_score_validation": True,
            "production_graph_mutation": False,
            "submission": False,
        },
        "cohort": {"complete": True, "expected_samples": 27, "observed_samples": 27},
    }
    report_path = tmp_path / "authorization.json"
    report_path.write_bytes(
        (json.dumps(report, indent=2) + "\n").replace("\n", "\r\n").encode("utf-8")
    )
    contract = {
        "authorization": {
            "report_normalized_sha256": _normalized_text_sha256(report_path),
            "evaluation_commit": "frozen-commit",
            "evaluated_arm": "e016_atabey_relink_v24_3_short_fragment_shadow",
        }
    }

    assert validate_full_27_authorization(report_path, contract) == report

    report["authorization"]["submission"] = True
    report_path.write_text(json.dumps(report), encoding="utf-8")
    contract["authorization"]["report_normalized_sha256"] = _normalized_text_sha256(
        report_path
    )
    with pytest.raises(RuntimeError, match="boundary"):
        validate_full_27_authorization(report_path, contract)


def test_collect_shards_requires_complete_disjoint_population(tmp_path):
    sample_ids = ["44b6_a", "6bba_b"]
    population_hash = hashlib.sha256("\n".join(sample_ids).encode("utf-8")).hexdigest()
    contract = {
        "population": {
            "shard_count": 2,
            "expected_samples": 2,
            "checkpoint_training_samples": 1,
            "held_out_samples": 1,
        }
    }
    shard_dirs = []
    for shard_index, (sample_id, usage) in enumerate(
        zip(sample_ids, ("held_out_27", "checkpoint_training_172"), strict=True)
    ):
        shard_dir = tmp_path / f"shard_{shard_index}"
        (shard_dir / "samples").mkdir(parents=True)
        (shard_dir / "summary.json").write_text(
            json.dumps(
                {
                    "decision": SHARD_COMPLETE,
                    "complete_shard": True,
                    "determinism_verified": True,
                    "shard_index": shard_index,
                    "expected_sample_count": 1,
                }
            ),
            encoding="utf-8",
        )
        (shard_dir / "provenance.json").write_text(
            json.dumps(
                {
                    "shard_index": shard_index,
                    "shard_count": 2,
                    "population_sample_ids_sha256": population_hash,
                }
            ),
            encoding="utf-8",
        )
        (shard_dir / "samples" / f"{sample_id}.json").write_text(
            json.dumps({"sample_id": sample_id, "checkpoint_usage": usage}),
            encoding="utf-8",
        )
        shard_dirs.append(shard_dir)

    records, provenance = collect_shard_records(shard_dirs, contract)

    assert [record["sample_id"] for record in records] == sample_ids
    assert provenance["shard_count"] == 2

    duplicate = json.loads(
        (shard_dirs[1] / "samples" / "6bba_b.json").read_text(encoding="utf-8")
    )
    duplicate["sample_id"] = "44b6_a"
    (shard_dirs[1] / "samples" / "6bba_b.json").write_text(
        json.dumps(duplicate), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="duplicate sample IDs"):
        collect_shard_records(shard_dirs, contract)
