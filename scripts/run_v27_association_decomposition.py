"""Prepare a reviewable V27A freeze candidate, or run an explicitly approved one."""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import gzip
from importlib import metadata
import json
from pathlib import Path
import platform
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from atabey.provenance import canonical_text_sha256, sha256_file
from atabey.tracking.association_factorial_audit import (
    ARMS, CONTRASTS, audit_factorial_frame, scientific_digest, summarize_rows,
)
from atabey.tracking.v24_2_shadow import prune_interior_isolated_detections
from atabey.tracking.v24_3_shadow import prune_interior_short_fragments
from run_v26_a_forward_ranking_ablation import (
    _graph_signature_sha256, _read_record, _reconstruct_frozen_relink, _selection_subtypes,
)

CONTRACT = "tests/fixtures/v27_association_causal_decomposition.json"
SCOPE = "V27A_FIXED_HISTORY_LOCAL_DECISIONS"


def runtime_identity() -> dict:
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            # Editable packages may be discovered repeatedly through duplicated
            # sys.path entries. Multiplicity is invocation state, not a version.
            "packages": sorted({(d.metadata["Name"], d.version) for d in metadata.distributions()})}


def required_source_paths(root: Path) -> set[str]:
    contract = json.loads((root / CONTRACT).read_text(encoding="utf-8"))
    paths = set(contract["reference_source_canonical_sha256"])
    paths.update(p.relative_to(root).as_posix() for p in (root / "src/atabey").rglob("*.py"))
    paths.update(p.relative_to(root).as_posix() for p in (root / "tests").glob("test_v27*.py"))
    paths.update({CONTRACT, "scripts/run_v27_association_decomposition.py",
                  "scripts/run_v25_upstream_association_forensics.py",
                  "scripts/run_v26_a_forward_ranking_ablation.py",
                  "tests/fixtures/v25_upstream_association_forensics.json", "pyproject.toml"})
    # Historical helpers import other runners. Pin that local import closure,
    # including imports inside functions, without freezing unrelated scripts.
    pending = [p for p in paths if p.startswith("scripts/") and p.endswith(".py")]
    seen = set()
    while pending:
        relative = pending.pop()
        if relative in seen:
            continue
        seen.add(relative)
        tree = ast.parse((root / relative).read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) else
                       [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                if module:
                    local = f"scripts/{module.split('.')[0]}.py"
                    if (root / local).is_file():
                        paths.add(local)
                        pending.append(local)
    return paths


def _safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise RuntimeError("Manifest path escapes repository")
    return path


def validate_science_contract(contract: dict) -> None:
    expected = {"H": ("exact_historical", "motion", "existing_ckdtree")}
    expected.update({a: ("filter_then_select" if f else "select_then_gate",
                         "physical_step" if r == "step" else r, "original_target_index")
                     for a, (f, r) in ARMS.items()})
    actual = {a["id"]: (a["order"], a["ranking"], a["forward_ties"]) for a in contract["arms"]}
    if len(contract["arms"]) != 5 or actual != expected:
        raise RuntimeError("V27 arm specification differs from implemented design")
    contrasts = {c["id"]: (c["before"], c["after"]) for c in contract["paired_contrasts"]}
    if len(contract["paired_contrasts"]) != 5 or contrasts != CONTRASTS:
        raise RuntimeError("V27 contrast specification mismatch")
    if contract["phase"] != SCOPE or contract["shared_controls"]["max_prediction_error_um"] != 9.0 or contract["shared_controls"]["max_step_distance_um"] != 9.0:
        raise RuntimeError("V27 scope or radius mismatch")


def verify_inputs(contract: dict, root: Path) -> dict:
    identities = {}
    for name, item in contract["inputs"].items():
        path = _safe_path(root, item["path"])
        actual = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        accepted = [item, *item.get("alternate_containers", [])]
        if not any(actual == {"bytes": a["bytes"], "sha256": a["sha256"]} for a in accepted):
            raise RuntimeError(f"Frozen input mismatch: {name}")
        identities[name] = actual
    return identities


def test_report_identity(path: Path) -> dict:
    tree = ET.parse(path)
    suites = list(tree.getroot().iter("testsuite"))
    totals = {key: sum(int(s.attrib.get(key, 0)) for s in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    if totals["tests"] == 0 or any(totals[k] for k in ("failures", "errors", "skipped")):
        raise RuntimeError("Freeze candidate requires completed passing tests without skips")
    return {"sha256": sha256_file(path), **totals}


def prepare_candidate(root: Path, test_report: Path) -> dict:
    contract = json.loads((root / CONTRACT).read_text(encoding="utf-8"))
    validate_science_contract(contract)
    for path, digest in contract["reference_source_canonical_sha256"].items():
        if canonical_text_sha256(_safe_path(root, path)) != digest:
            raise RuntimeError(f"Proposed scientific reference changed: {path}")
    test_path = test_report.resolve().relative_to(root.resolve()).as_posix()
    payload = {
        "scope": SCOPE, "builder": "Codex", "contract_path": CONTRACT,
        "canonical_sources": {p: canonical_text_sha256(root / p) for p in sorted(required_source_paths(root))},
        "inputs": verify_inputs(contract, root), "runtime": runtime_identity(),
        "test_report": {"path": test_path, **test_report_identity(test_report)},
    }
    return {"status": "READY_FOR_HUMAN_REVIEW", "payload": payload,
            "payload_sha256": scientific_digest(payload), "review": None,
            "human_execution_authorization": None}


def validate_freeze(manifest: dict, root: Path) -> dict:
    if manifest.get("status") != "FROZEN":
        raise RuntimeError("V27 freeze is not FROZEN; proposal/candidate cannot execute")
    payload = manifest["payload"]
    digest = scientific_digest(payload)
    if manifest.get("payload_sha256") != digest or payload["scope"] != SCOPE:
        raise RuntimeError("Freeze payload integrity/scope mismatch")
    review, authorization = manifest.get("review"), manifest.get("human_execution_authorization")
    if not isinstance(review, dict) or not isinstance(authorization, dict):
        raise RuntimeError("Missing human review or execution authorization record")
    if (not review.get("reviewer") or review["reviewer"] == payload["builder"]
            or review.get("reviewed_payload_sha256") != digest or not review.get("record")):
        raise RuntimeError("Review must identify a reviewer distinct from builder and the exact payload")
    if (not authorization.get("authority") or not authorization.get("record")
            or authorization.get("approved_payload_sha256") != digest or authorization.get("scope") != SCOPE):
        raise RuntimeError("Human authorization does not cover this exact V27A payload")
    if payload["contract_path"] != CONTRACT:
        raise RuntimeError("Unexpected scientific contract")
    if not required_source_paths(root).issubset(payload["canonical_sources"]):
        raise RuntimeError("Freeze omits required scientific/implementation sources")
    for path, expected in payload["canonical_sources"].items():
        if canonical_text_sha256(_safe_path(root, path)) != expected:
            raise RuntimeError(f"Frozen source mismatch: {path}")
    # JSON normalizes tuples to arrays; compare canonical digests, not Python types.
    if scientific_digest(payload["runtime"]) != scientific_digest(runtime_identity()):
        raise RuntimeError("Frozen runtime mismatch")
    report = payload["test_report"]
    if test_report_identity(_safe_path(root, report["path"])) != {k: v for k, v in report.items() if k != "path"}:
        raise RuntimeError("Frozen test evidence mismatch")
    contract = json.loads((root / CONTRACT).read_text(encoding="utf-8"))
    validate_science_contract(contract)
    return contract


def write_json_new(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n")


def replay_sample(record: dict, graph, output: Path) -> dict:
    """Stream frame records; frozen predecessor map is never updated by an arm."""
    before = _graph_signature_sha256(graph)
    nodes = {n.node_id: n for n in graph.detections}
    frames = defaultdict(list)
    for n in graph.detections:
        frames[n.t].append(n)
    predecessors = {}
    for edge in graph.edges:
        if edge.target_id in predecessors or nodes[edge.target_id].t != nodes[edge.source_id].t + 1:
            raise RuntimeError("Frozen baseline history has ambiguous/nonadjacent predecessor")
        predecessors[edge.target_id] = nodes[edge.source_id]
    subtypes = _selection_subtypes(record, graph)
    loss_by_source = defaultdict(list)
    for loss in record["v19_credited_v24_3_lost_edges"]:
        gt = (loss["ground_truth_source_id"], loss["ground_truth_target_id"])
        for source in loss["matched_e016_source_ids"]:
            loss_by_source[source].append({"ground_truth_edge": list(gt),
                                           "subtype": subtypes.get(gt, loss["failure_class"])})
    counts, historical_edges = Counter(), set()
    with output.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for t in range(max(frames, default=0)):
                previous = frames[t]
                local_parents = {n.node_id: predecessors[n.node_id] for n in previous if n.node_id in predecessors}
                frame = audit_factorial_frame(previous, frames[t + 1], local_parents)
                for row in frame["rows"]:
                    row["archived_loss_memberships"] = loss_by_source[row["source_id"]]
                    target = row["decisions"]["H"]["accepted_target_id"]
                    if target is not None:
                        historical_edges.add((row["source_id"], target))
                stream.write((json.dumps(frame, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode())
                if frame["validity_failures"]:
                    raise RuntimeError(f"V27 frame validity failure in {record['sample_id']} t={t}: {frame['validity_failures']}")
                counts.update(summarize_rows(frame["rows"]))
    if historical_edges != {(e.source_id, e.target_id) for e in graph.edges}:
        raise RuntimeError("Historical edge identity census mismatch")
    if _graph_signature_sha256(graph) != before:
        raise RuntimeError("Frozen graph changed during census")
    return {"counts": dict(sorted(counts.items())), "graph_sha256": before,
            "frame_stream_sha256": sha256_file(output), "graph_unchanged": True}


def execute(manifest_path: Path, approved_manifest_sha256: str, output: Path, root: Path = ROOT) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    partial = []
    try:
        if not approved_manifest_sha256 or sha256_file(manifest_path) != approved_manifest_sha256:
            raise RuntimeError("Explicit approved freeze SHA-256 is required and must match")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        contract = validate_freeze(manifest, root)
        actual_inputs = verify_inputs(contract, root)
        if actual_inputs != manifest["payload"]["inputs"]:
            raise RuntimeError("Selected archive container differs from frozen payload")
        write_json_new(output / "freeze_used.json", manifest)
        sample_ids = contract["cohort"]["sample_ids"]
        if len(sample_ids) != 16 or len(set(sample_ids)) != 16:
            raise RuntimeError("Incomplete or duplicate cohort")
        with zipfile.ZipFile(root / contract["inputs"]["v25_archive"]["path"]) as v25, \
                zipfile.ZipFile(root / contract["inputs"]["v26a_archive"]["path"]) as v26:
            for archive, prefix, count in ((v25, "run/samples/", 27), (v26, "samples/", 19)):
                names = archive.namelist()
                sample_names = {n for n in names if n.startswith(prefix) and n.endswith(".json.gz")}
                if (len(names) != count or len(names) != len(set(names)) or
                        sample_names != {f"{prefix}{s}.json.gz" for s in sample_ids}):
                    raise RuntimeError("Archive entry/cohort mismatch")
            for index, sample_id in enumerate(sample_ids, 1):
                print(f"[{index}/16] {sample_id}: V27A frozen-history replay", flush=True)
                record = _read_record(v25, sample_id)
                old = json.loads(gzip.decompress(v26.read(f"samples/{sample_id}.json.gz")))
                if record["sample_id"] != sample_id or old["sample_id"] != sample_id:
                    raise RuntimeError("Sample identity mismatch")
                graph = _reconstruct_frozen_relink(record)
                v24_2 = prune_interior_isolated_detections(graph)
                v24_3 = prune_interior_short_fragments(v24_2)
                for name, stage in (("relink", graph), ("v24_2", v24_2), ("v24_3", v24_3)):
                    if _graph_signature_sha256(stage) != record["graph_signatures"][f"{name}_sha256"]:
                        raise RuntimeError(f"Frozen graph signature mismatch: {sample_id}/{name}")
                if _graph_signature_sha256(v24_3) != old["graph_signatures"]["baseline_v24_3_sha256"]:
                    raise RuntimeError("Historical V26A baseline mismatch")
                first = replay_sample(record, graph, output / f"{sample_id}.pass1.jsonl.gz")
                second = replay_sample(record, graph, output / f"{sample_id}.pass2.jsonl.gz")
                if first != second:
                    raise RuntimeError(f"Nondeterministic scientific replay: {sample_id}")
                result = {"sample_id": sample_id, **first, "deterministic_replay": True,
                          "verified_graph_signatures": record["graph_signatures"]}
                write_json_new(output / f"{sample_id}.summary.json", result)
                partial.append(result)
        totals = Counter()
        for sample in partial:
            totals.update(sample["counts"])
        expected = {"sources": 99167, "accepted::H": 86778, "gate_order_exposed": 229, "exposed_s1_accepted": 200}
        if any(totals[k] != v for k, v in expected.items()):
            raise RuntimeError("Frozen gate-order audit denominator mismatch")
        # Recheck files/runtime after execution, not only at startup.
        validate_freeze(manifest, root)
        if verify_inputs(contract, root) != actual_inputs:
            raise RuntimeError("Input evidence changed during execution")
        result = {"status": "VALID_MECHANISM_RESULT", "scope": SCOPE, "sample_count": len(partial),
                  "verified_baseline_signatures": 48, "counts": dict(sorted(totals.items())),
                  "samples": partial, "approved_freeze_sha256": approved_manifest_sha256,
                  "production_tuning_authorized": False, "submission_authorized": False,
                  "v26a_decision_preserved": "NO_GO"}
        write_json_new(output / "summary.json", result)
        return result
    except Exception as exc:
        write_json_new(output / "invalid_execution.json", {
            "status": "INVALID_EXECUTION", "error_type": type(exc).__name__, "error": str(exc),
            "completed_samples": partial, "production_tuning_authorized": False,
            "submission_authorized": False, "v26a_decision_preserved": "NO_GO",
        })
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare-freeze")
    prepare.add_argument("--test-report", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--freeze", type=Path, required=True)
    run.add_argument("--approved-freeze-sha256", required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare-freeze":
        if args.output.exists():
            raise FileExistsError("Preserve existing freeze candidate")
        candidate = prepare_candidate(ROOT, args.test_report)
        write_json_new(args.output, candidate)
        print(f"READY_FOR_HUMAN_REVIEW payload={candidate['payload_sha256']}")
    else:
        execute(args.freeze, args.approved_freeze_sha256, args.output_dir)


if __name__ == "__main__":
    main()
