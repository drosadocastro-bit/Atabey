import hashlib
import json
from pathlib import Path

from atabey.provenance import canonical_text_sha256


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "v24_8_independent_cohort_eligibility_audit.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v24_8_audit_pins_its_sources() -> None:
    audit = _load(AUDIT)

    for source in audit["sources"].values():
        assert canonical_text_sha256(ROOT / source["path"]) == source[
            "canonical_sha256"
        ]


def test_v24_8_audit_accounts_for_every_labeled_sample() -> None:
    audit = _load(AUDIT)
    manifest = _load(ROOT / audit["sources"]["labeled_manifest"]["path"])
    sample_ids = sorted(
        set(manifest["training_sample_ids"])
        | set(manifest["held_out_development_sample_ids"])
    )
    population_hash = hashlib.sha256("\n".join(sample_ids).encode("utf-8")).hexdigest()

    assert len(sample_ids) == audit["inventory"]["labeled_samples"] == 199
    assert population_hash == audit["sources"]["full_population_report"][
        "population_sample_ids_sha256"
    ]
    assert audit["inventory"]["opened_full_population_samples"] == len(sample_ids)
    assert audit["inventory"]["labeled_samples_not_opened"] == 0
    assert audit["inventory"]["eligible_labeled_repository_samples"] == 0


def test_v24_8_internal_validation_split_is_not_independent() -> None:
    audit = _load(AUDIT)
    manifest = _load(ROOT / audit["sources"]["labeled_manifest"]["path"])
    split = _load(ROOT / audit["sources"]["internal_split"]["path"])[0]
    internal_validation_ids = {
        sample.removesuffix(".zarr") for sample in split["test"]
    }

    assert len(internal_validation_ids) == 34
    assert internal_validation_ids <= set(manifest["training_sample_ids"])
    assert audit["inventory"][
        "historical_internal_validation_within_checkpoint_training"
    ] == len(internal_validation_ids)


def test_v24_8_execution_remains_fail_closed() -> None:
    audit = _load(AUDIT)

    assert audit["decision"] == "NO_QUALIFYING_INDEPENDENT_COHORT_AVAILABLE"
    assert all(value is False for value in audit["boundaries"].values())