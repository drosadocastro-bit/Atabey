import ast
from copy import deepcopy
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from atabey.constants import DEFAULT_VOXEL_SCALE_UM
from atabey.provenance import canonical_text_sha256, sha256_file
from atabey.tracking import association_factorial_audit as parent
from atabey.tracking import association_factorial_audit_v27a1 as amended
from atabey.types import Detection

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_v27_association_decomposition as old_runner
import run_v27a1_association_decomposition as runner


@pytest.fixture
def witness():
    fixture = json.loads((ROOT / "tests/fixtures/v27a1_exact_tie_gate_witness.json").read_text())
    def detection(row):
        z, y, x = row["position_um"]
        return Detection(row["node_id"], fixture["sample_id"], row["t"],
                         z / DEFAULT_VOXEL_SCALE_UM.z, y / DEFAULT_VOXEL_SCALE_UM.y,
                         x / DEFAULT_VOXEL_SCALE_UM.x, z, y, x)
    inputs = ([detection(n) for n in fixture["previous"]],
              [detection(n) for n in fixture["current"]],
              {k: detection(v) for k, v in fixture["predecessors"].items()})
    return fixture, inputs


def test_known_failure_stays_invalid_under_parent_and_preserves_exact_decisions(witness):
    fixture, inputs = witness
    before = deepcopy(inputs)
    original = parent.audit_factorial_frame(*inputs)
    assert original["validity_failures"] == [fixture["expected_original_failure"]]
    original_before = deepcopy(original)
    new = amended.apply_amendment(original)
    assert original == original_before and inputs == before
    assert new["validity_failures"] == []
    assert new["parent_v27a_validity_failures"] == original["validity_failures"]
    assert new["parent_observation_sha256"] == parent.scientific_digest(original)
    for old_row, new_row in zip(original["rows"], new["rows"]):
        assert {k: v for k, v in new_row.items() if k != "v27a1_gate_review"} == old_row
    for key in original:
        if key not in ("validity_failures", "rows"):
            assert new[key] == original[key]
    row = next(r for r in new["rows"] if r["source_id"] == fixture["witness_source_id"])
    assert row["decisions"] == fixture["expected_witness_decisions"]
    assert row["v27a1_gate_review"]["classification"] == "EXACT_TIE_DIFFERENT_ELIGIBILITY"
    assert new["parent_criterion_dispositions"] == [{"parent_failure": fixture["expected_original_failure"],
        "disposition": "RECORDED_TIE_MEDIATED_OUTCOME"}]
    assert amended.summarize_rows(new["rows"])["v27a1_gate_review::EXACT_TIE_DIFFERENT_ELIGIBILITY"] == 1


def test_witness_fixture_is_linked_to_preserved_real_failure(witness):
    fixture, _ = witness
    assert fixture["kind"] == "KNOWN_OPENED_FAILURE_REGRESSION_WITNESS"
    assert sha256_file(ROOT / fixture["provenance"]["raw_stream_path"]) == fixture["provenance"]["raw_stream_sha256"]
    manifest = json.loads((ROOT / "v27a_freeze_approved_20260924.json").read_text())
    for path, digest in manifest["payload"]["canonical_sources"].items():
        assert canonical_text_sha256(ROOT / path) == digest


@pytest.mark.parametrize("check", ["H_executable_anchor_mismatch", "S1_executable_anchor_mismatch",
                                  "h_m0_confidence_mismatch", "h_m0_non_tie_selection", "input_mutation"])
def test_other_parent_failures_remain_binding(witness, check):
    fixture, inputs = witness
    original = parent.audit_factorial_frame(*inputs)
    failure = {"source_id": fixture["witness_source_id"], "check": check}
    original["validity_failures"].append(failure)
    new = amended.apply_amendment(original)
    assert failure in new["validity_failures"]
    assert failure in new["parent_v27a_validity_failures"]


def synthetic_tie_frame(good_first=True):
    targets = [[0., 0., 0.], [0., 0., 10.]] if good_first else [[0., 0., 10.], [0., 0., 0.]]
    choices = {}
    for arm, index in (("H", 1), ("M0", 0)):
        step = targets[index][2]
        eligible = step <= 9
        choices[arm] = {"selected_index": index, "selected_target_id": f"t{index}",
            "prediction_error_um": 5., "physical_step_um": step,
            "gate_eligible_target_id": f"t{index}" if eligible else None,
            "accepted_target_id": f"t{index}" if eligible else None,
            "confidence": 1 - 5 / 9 if eligible else None}
    row = {"source_id": "s", "predicted_position_um": [0., 0., 5.],
           "prediction_errors_um": [5., 5.], "physical_steps_um": [p[2] for p in targets], "decisions": choices}
    return {"source_ids": ["s"], "source_positions_um": [[0., 0., 0.]],
            "target_ids": ["t0", "t1"], "target_positions_um": targets,
            "rows": [row], "validity_failures": [{"source_id": "s", "check": "h_m0_gate_mismatch"}]}


@pytest.mark.parametrize("good_first", [True, False])
def test_exact_tie_allows_opposite_eligibility_in_either_direction(good_first):
    original = synthetic_tie_frame(good_first)
    result = amended.apply_amendment(original)
    assert result["validity_failures"] == []
    assert result["rows"][0]["v27a1_gate_review"]["classification"] == "EXACT_TIE_DIFFERENT_ELIGIBILITY"
    assert original["validity_failures"]


def test_same_candidate_inconsistent_predicate_is_not_admitted():
    original = synthetic_tie_frame()
    original["rows"][0]["decisions"]["H"] = deepcopy(original["rows"][0]["decisions"]["M0"])
    original["rows"][0]["decisions"]["H"]["gate_eligible_target_id"] = None
    result = amended.apply_amendment(original)
    assert original["validity_failures"][0] in result["validity_failures"]
    assert result["rows"][0]["v27a1_gate_review"]["classification"] == "INVALID_EVIDENCE"


@pytest.mark.parametrize("field,value", [("selected_target_id", "wrong-id"),
    ("prediction_error_um", 5.000000000001), ("physical_step_um", 9.), ("confidence", .99)])
def test_inconsistent_candidate_evidence_is_not_admitted(field, value):
    original = synthetic_tie_frame(False)  # H selects the eligible target.
    original["rows"][0]["decisions"]["H"][field] = value
    result = amended.apply_amendment(original)
    assert original["validity_failures"][0] in result["validity_failures"]
    assert result["rows"][0]["v27a1_gate_review"]["classification"] == "INVALID_EVIDENCE"


@pytest.mark.parametrize("delta", [1e-12, .01])
def test_near_ties_are_not_exact_ties(delta):
    original = synthetic_tie_frame()
    original["target_positions_um"][1][2] += delta
    row = original["rows"][0]
    error = float(np.linalg.norm(np.array(original["target_positions_um"][1]) - row["predicted_position_um"]))
    step = original["target_positions_um"][1][2]
    row["prediction_errors_um"][1] = error
    row["physical_steps_um"][1] = step
    row["decisions"]["H"].update(prediction_error_um=error, physical_step_um=step)
    result = amended.apply_amendment(original)
    assert result["validity_failures"]
    assert result["rows"][0]["v27a1_gate_review"]["classification"] == "INVALID_EVIDENCE"


def test_equal_eligibility_tie_is_a_separate_classification():
    original = synthetic_tie_frame()
    original["source_positions_um"] = [[0., 0., 5.]]
    row = original["rows"][0]
    row["physical_steps_um"] = [5., 5.]
    for arm, d in row["decisions"].items():
        d.update(physical_step_um=5., gate_eligible_target_id=d["selected_target_id"],
                 accepted_target_id=d["selected_target_id"], confidence=1 - 5 / 9)
    original["validity_failures"] = []
    result = amended.apply_amendment(original)
    assert not result["validity_failures"]
    assert result["rows"][0]["v27a1_gate_review"]["classification"] == "EXACT_TIE_SAME_ELIGIBILITY"


def test_empty_frame_and_determinism(witness):
    assert amended.audit_factorial_frame([], [], {})["validity_failures"] == []
    _, inputs = witness
    assert amended.audit_factorial_frame(*inputs) == amended.audit_factorial_frame(*inputs)


def test_runner_replay_and_execution_pipeline_are_unchanged():
    def definitions(path):
        tree = ast.parse(path.read_text())
        return {n.name: ast.dump(n, include_attributes=False) for n in tree.body if isinstance(n, ast.FunctionDef)}
    old = definitions(ROOT / "scripts/run_v27_association_decomposition.py")
    new = definitions(ROOT / "scripts/run_v27a1_association_decomposition.py")
    for name in ("replay_sample", "execute", "validate_freeze", "verify_inputs", "runtime_identity", "test_report_identity"):
        assert new[name] == old[name]
    assert runner.audit_factorial_frame is amended.audit_factorial_frame
    assert old_runner.audit_factorial_frame is parent.audit_factorial_frame


def test_parent_approval_does_not_authorize_new_scope():
    old = json.loads((ROOT / "v27a_freeze_approved_20260924.json").read_text())
    with pytest.raises(RuntimeError, match="scope mismatch"):
        runner.validate_freeze(old, ROOT)


def test_amendment_candidate_is_not_executable(tmp_path):
    path = tmp_path / "candidate.json"
    runner.write_json_new(path, {"status": "READY_FOR_HUMAN_REVIEW"})
    with pytest.raises(RuntimeError, match="not FROZEN"):
        runner.execute(path, sha256_file(path), tmp_path / "attempt")
    failure = json.loads((tmp_path / "attempt/invalid_execution.json").read_text())
    assert failure["status"] == "INVALID_EXECUTION" and not failure["completed_samples"]


def test_new_contract_preserves_factorial_and_radii_and_requires_amendment():
    contract = json.loads((ROOT / runner.CONTRACT).read_text())
    runner.validate_science_contract(contract)
    old = json.loads((ROOT / old_runner.CONTRACT).read_text())
    for key in ("arms", "paired_contrasts", "cohort", "shared_controls", "interaction", "boundaries"):
        assert contract[key] == old[key]
    del contract["amendment"]
    with pytest.raises(RuntimeError, match="amendment identity"):
        runner.validate_science_contract(contract)
