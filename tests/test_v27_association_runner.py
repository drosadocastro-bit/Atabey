from copy import deepcopy
import gzip
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_v27_association_decomposition as runner
from atabey.provenance import canonical_text_sha256, sha256_file
from atabey.tracking.association_factorial_audit import scientific_digest
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints
from atabey.types import Detection, LineageGraph


def node(name, t, y):
    return Detection(name, "synthetic", t, 0, y, 0, 0, y, 0)


def test_frame_replay_never_propagates_alternative_predecessors(tmp_path):
    frames = [[node("p", 0, -4)], [node("s", 1, 0)],
              [node("a", 2, 1), node("b", 2, 4)], [node("next", 3, 2)]]
    graph = LineageGraph("synthetic", detections=[n for frame in frames for n in frame])
    parents = {}
    for prev, curr in zip(frames, frames[1:]):
        edges = link_adjacent_timepoints(prev, curr, 9, strategy="motion_mutual", predecessor_by_node_id=parents)
        graph.edges.extend(edges)
        lookup = {n.node_id: n for n in prev}
        for e in edges:
            parents[e.target_id] = lookup[e.source_id]
    before = deepcopy(graph)
    record = {"sample_id": "synthetic", "v19_credited_v24_3_lost_edges": []}
    first_path, second_path = tmp_path / "first.gz", tmp_path / "second.gz"
    first = runner.replay_sample(record, graph, first_path)
    second = runner.replay_sample(record, graph, second_path)
    assert first == second and first_path.read_bytes() == second_path.read_bytes()
    rows = [json.loads(line) for line in gzip.decompress(first_path.read_bytes()).splitlines()]
    s = rows[1]["rows"][0]
    assert s["decisions"]["S0"]["accepted_target_id"] == "a"
    assert s["decisions"]["H"]["accepted_target_id"] == "b"
    a = next(r for r in rows[2]["rows"] if r["source_id"] == "a")
    assert a["predecessor_id"] is None  # S0's preceding choice was never fed back.
    assert graph == before
    with pytest.raises(FileExistsError):
        runner.replay_sample(record, graph, first_path)


def test_frame_failure_is_saved_before_execution_stops(tmp_path, monkeypatch):
    graph = LineageGraph("synthetic", detections=[node("s", 0, 0), node("t", 1, 1)])
    monkeypatch.setattr(runner, "audit_factorial_frame", lambda *args: {
        "rows": [], "validity_failures": [{"check": "explicit_synthetic_failure"}]})
    path = tmp_path / "partial.gz"
    with pytest.raises(RuntimeError, match="explicit_synthetic_failure"):
        runner.replay_sample({"sample_id": "synthetic", "v19_credited_v24_3_lost_edges": []}, graph, path)
    assert json.loads(gzip.decompress(path.read_bytes()))["validity_failures"] == [
        {"check": "explicit_synthetic_failure"}]


def test_real_execution_entry_rejects_candidate_and_preserves_failure(tmp_path):
    candidate = tmp_path / "candidate.json"
    runner.write_json_new(candidate, {"status": "READY_FOR_HUMAN_REVIEW"})
    output = tmp_path / "attempt"
    with pytest.raises(RuntimeError, match="not FROZEN"):
        runner.execute(candidate, sha256_file(candidate), output)
    result = json.loads((output / "invalid_execution.json").read_text())
    assert result["status"] == "INVALID_EXECUTION" and result["completed_samples"] == []
    with pytest.raises(FileExistsError):
        runner.execute(candidate, sha256_file(candidate), output)


def test_missing_explicit_manifest_digest_rejected(tmp_path):
    candidate = tmp_path / "candidate.json"
    runner.write_json_new(candidate, {"status": "FROZEN"})
    with pytest.raises(RuntimeError, match="approved freeze SHA-256"):
        runner.execute(candidate, "", tmp_path / "attempt")


@pytest.fixture
def synthetic_freeze(tmp_path, monkeypatch):
    """Explicit fake review records, only in an isolated test repository."""
    root = tmp_path / "repo"
    for rel in runner.required_source_paths(ROOT):
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dest)
    report = root / "synthetic-tests.xml"
    report.write_text('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"/></testsuites>')
    runtime = {"explicit_test_runtime": True}
    monkeypatch.setattr(runner, "runtime_identity", lambda: runtime)
    payload = {"scope": runner.SCOPE, "builder": "explicit_test_builder", "contract_path": runner.CONTRACT,
               "canonical_sources": {p: canonical_text_sha256(root / p) for p in runner.required_source_paths(root)},
               "runtime": runtime, "test_report": {"path": report.name, **runner.test_report_identity(report)}}
    digest = scientific_digest(payload)
    manifest = {"status": "FROZEN", "payload": payload, "payload_sha256": digest,
                "review": {"reviewer": "explicit_test_reviewer", "record": "synthetic unit-test record",
                           "reviewed_payload_sha256": digest},
                "human_execution_authorization": {"authority": "explicit_test_authority",
                    "record": "synthetic unit-test record", "scope": runner.SCOPE, "approved_payload_sha256": digest}}
    return root, manifest


def test_explicit_synthetic_freeze_validates_without_executing_data(synthetic_freeze):
    root, manifest = synthetic_freeze
    assert runner.validate_freeze(manifest, root)["phase"] == runner.SCOPE


@pytest.mark.parametrize("field", ["review", "human_execution_authorization"])
def test_missing_review_or_authority_rejected(synthetic_freeze, field):
    root, manifest = synthetic_freeze
    manifest[field] = None
    with pytest.raises(RuntimeError, match="Missing human"):
        runner.validate_freeze(manifest, root)


def test_builder_cannot_supply_its_own_review(synthetic_freeze):
    root, manifest = synthetic_freeze
    manifest["review"]["reviewer"] = manifest["payload"]["builder"]
    with pytest.raises(RuntimeError, match="distinct from builder"):
        runner.validate_freeze(manifest, root)


def test_changed_frozen_source_rejected(synthetic_freeze):
    root, manifest = synthetic_freeze
    (root / "src/atabey/tracking/association_factorial_audit.py").write_text("changed scientific implementation")
    with pytest.raises(RuntimeError, match="Frozen source mismatch"):
        runner.validate_freeze(manifest, root)


def test_unreviewed_payload_change_rejected(synthetic_freeze):
    root, manifest = synthetic_freeze
    manifest["payload"]["builder"] = "different"
    with pytest.raises(RuntimeError, match="payload integrity"):
        runner.validate_freeze(manifest, root)


def test_runtime_drift_rejected(synthetic_freeze, monkeypatch):
    root, manifest = synthetic_freeze
    monkeypatch.setattr(runner, "runtime_identity", lambda: {"different": True})
    with pytest.raises(RuntimeError, match="runtime mismatch"):
        runner.validate_freeze(manifest, root)


def test_freeze_cannot_omit_required_sources(synthetic_freeze):
    root, manifest = synthetic_freeze
    manifest["payload"]["canonical_sources"].pop("src/atabey/tracking/association_factorial_audit.py")
    digest = scientific_digest(manifest["payload"])
    manifest["payload_sha256"] = digest
    manifest["review"]["reviewed_payload_sha256"] = digest
    manifest["human_execution_authorization"]["approved_payload_sha256"] = digest
    with pytest.raises(RuntimeError, match="omits required"):
        runner.validate_freeze(manifest, root)


def test_proposal_scientific_factor_change_is_rejected():
    contract = json.loads((ROOT / runner.CONTRACT).read_text())
    contract["arms"][2]["ranking"] = "physical_step"
    with pytest.raises(RuntimeError, match="arm specification"):
        runner.validate_science_contract(contract)


def test_failed_synthetic_test_report_cannot_prepare_freeze(tmp_path):
    path = tmp_path / "failed.xml"
    path.write_text('<testsuite tests="2" failures="1"/>')
    with pytest.raises(RuntimeError, match="passing tests"):
        runner.test_report_identity(path)


def test_freeze_includes_transitive_historical_runner_imports():
    required = runner.required_source_paths(ROOT)
    assert {"scripts/run_v21_division_recovery_shadow.py",
            "scripts/run_v22_unet_detection_shadow.py",
            "scripts/run_v24_score_first_tracking.py"}.issubset(required)


def test_runtime_identity_ignores_duplicate_discovery_but_preserves_versions(monkeypatch):
    class Distribution:
        def __init__(self, version):
            self.metadata = {"Name": "explicit-synthetic-package"}
            self.version = version
    monkeypatch.setattr(runner.metadata, "distributions", lambda: [Distribution("1"), Distribution("1")])
    first = runner.runtime_identity()
    monkeypatch.setattr(runner.metadata, "distributions", lambda: [Distribution("1")])
    assert runner.runtime_identity() == first
    monkeypatch.setattr(runner.metadata, "distributions", lambda: [Distribution("1"), Distribution("2")])
    assert runner.runtime_identity() != first
