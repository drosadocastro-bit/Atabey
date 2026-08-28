from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_v24_3_full_199_score_validation import (
    ARMS,
    ARM_V19,
    ARM_V24_3,
    SHARD_COMPLETE,
    _atomic_json,
    _comparison,
    _summaries,
    _write_csv,
    validate_frozen_sources,
)


COMPLETE = "FULL_199_SCORE_VALIDATION_COMPLETE"


def collect_shard_records(
    shard_dirs: list[Path], contract: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_shards = contract["population"]["shard_count"]
    if len(shard_dirs) != expected_shards:
        raise RuntimeError(f"expected {expected_shards} shard directories")

    records: list[dict[str, Any]] = []
    indexes: set[int] = set()
    canonical_provenance: dict[str, Any] | None = None
    for shard_dir in shard_dirs:
        summary = json.loads((shard_dir / "summary.json").read_text(encoding="utf-8"))
        provenance = json.loads(
            (shard_dir / "provenance.json").read_text(encoding="utf-8")
        )
        if (
            summary.get("decision") != SHARD_COMPLETE
            or summary.get("complete_shard") is not True
            or summary.get("determinism_verified") is not True
        ):
            raise RuntimeError(f"incomplete or nondeterministic shard: {shard_dir}")
        shard_index = int(summary["shard_index"])
        if shard_index in indexes:
            raise RuntimeError(f"duplicate shard index: {shard_index}")
        indexes.add(shard_index)

        comparable = {key: value for key, value in provenance.items() if key != "shard_index"}
        if canonical_provenance is None:
            canonical_provenance = comparable
        elif comparable != canonical_provenance:
            raise RuntimeError("shard provenance mismatch")

        paths = sorted((shard_dir / "samples").glob("*.json"))
        if len(paths) != summary["expected_sample_count"]:
            raise RuntimeError(f"shard sample count mismatch: {shard_dir}")
        records.extend(json.loads(path.read_text(encoding="utf-8")) for path in paths)

    if indexes != set(range(expected_shards)):
        raise RuntimeError(f"shard indexes are incomplete: {sorted(indexes)}")
    sample_ids = [record["sample_id"] for record in records]
    if len(sample_ids) != len(set(sample_ids)):
        raise RuntimeError("duplicate sample IDs across shards")
    if len(sample_ids) != contract["population"]["expected_samples"]:
        raise RuntimeError("merged population sample count mismatch")
    population_hash = hashlib.sha256(
        "\n".join(sorted(sample_ids)).encode("utf-8")
    ).hexdigest()
    if canonical_provenance is None or (
        population_hash != canonical_provenance["population_sample_ids_sha256"]
    ):
        raise RuntimeError("merged population ID hash mismatch")

    usage_counts = {
        label: sum(record.get("checkpoint_usage") == label for record in records)
        for label in ("checkpoint_training_172", "held_out_27")
    }
    if usage_counts != {
        "checkpoint_training_172": contract["population"]["checkpoint_training_samples"],
        "held_out_27": contract["population"]["held_out_samples"],
    }:
        raise RuntimeError(f"checkpoint-usage strata mismatch: {usage_counts}")
    return sorted(records, key=lambda record: record["sample_id"]), canonical_provenance


def _arm_result(records: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    reference = _summaries(records, ARM_V19)
    challenger = _summaries(records, arm)
    comparison = _comparison(records, arm)
    comparison.update(
        {
            "pooled_adjusted_edge_delta": (
                challenger["overall"]["adjusted_edge_jaccard"]
                - reference["overall"]["adjusted_edge_jaccard"]
            ),
            "pooled_total_score_delta": (
                challenger["overall"]["score"] - reference["overall"]["score"]
            ),
        }
    )
    return {"summary": challenger, "vs_v19": comparison}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge two frozen V24.3 full-199 score-validation shards."
    )
    parser.add_argument("--shard-dirs", type=Path, nargs="+", required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "tests/fixtures/v24_3_full_199_score_validation.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    validate_frozen_sources(contract)
    records, provenance = collect_shard_records(args.shard_dirs, contract)
    training_records = [
        record
        for record in records
        if record["checkpoint_usage"] == "checkpoint_training_172"
    ]
    held_out_records = [
        record for record in records if record["checkpoint_usage"] == "held_out_27"
    ]

    summary = {
        "status": "v24_3_full_199_score_validation_result",
        "decision": COMPLETE,
        "sample_count": len(records),
        "complete_population": True,
        "all_shards_deterministic": True,
        "arms": {arm: _arm_result(records, arm) for arm in ARMS},
        "v24_3_by_checkpoint_usage": {
            "checkpoint_training_172": _arm_result(training_records, ARM_V24_3),
            "held_out_27": _arm_result(held_out_records, ARM_V24_3),
        },
        "population_interpretation": (
            "The 172 checkpoint-training samples are population score context, not "
            "independent generalization evidence."
        ),
        "assignment_enabled": False,
        "hybrid_enabled": False,
        "production_graph_mutation": False,
        "submission_authorized": False,
        "provenance": provenance,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(args.output_dir / "summary.json", summary)
    _write_csv(args.output_dir / "per_sample.csv", records)
    for record in records:
        _atomic_json(
            args.output_dir / "samples" / f"{record['sample_id']}.json", record
        )
    print(
        json.dumps(
            {
                "decision": summary["decision"],
                "sample_count": summary["sample_count"],
                "complete_population": summary["complete_population"],
                "submission_authorized": summary["submission_authorized"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
