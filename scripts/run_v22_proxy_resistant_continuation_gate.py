from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from atabey.tracking.continuation_head import evaluate_generalization
from fit_v22_continuation_head_oof import (
    DECISION_ROUTES,
    LOCAL_MAXIMA_ROUTE,
    Preprocessor,
    _fit_oof,
    _group_weights,
    _load_samples,
    _report_strata,
    _score_samples,
)

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixed_nearest_distance(samples, feature_names, head_contract):
    index = np.array([feature_names.index("parent_child_distance_um")], dtype=np.int64)
    preprocessor = Preprocessor(medians=np.array([0.0]), means=np.array([0.0]), scales=np.array([1.0]))
    coefficients = np.array([-1.0, 0.0])
    sample_rows, group_rows = _score_samples(
        samples, preprocessor, index, coefficients,
        float(head_contract["evaluation"]["strict_score_tie_tolerance"]),
    )
    return {
        "model": "fixed_nearest_distance",
        "metrics": _report_strata(sample_rows, [1, 2, 3]),
        "per_sample": sorted(sample_rows, key=lambda row: row["sample_id"]),
        "group_rows": group_rows,
    }


def _random_expectation(samples):
    rows = []
    for sample in samples:
        weights = _group_weights(sample)
        top1 = 0.0
        mrr = 0.0
        for group in sample.groups:
            count = group.stop - group.start
            if count < 2:
                continue
            weight = weights[group.reference_id]
            top1 += weight / count
            mrr += weight * sum(1.0 / rank for rank in range(1, count + 1)) / count
        rows.append({
            "sample_id": sample.sample_id, "fold": sample.fold, "family": sample.family,
            "route": sample.route, "nontrivial_groups": len(weights),
            "singleton_groups": sample.reference_count - len(weights),
            "reference_top1": top1, "pairwise_accuracy": 0.5, "mrr": mrr,
        })
    return {"model": "random_within_group_expectation", "metrics": _report_strata(rows, [1, 2, 3]), "per_sample": rows}


def _metric_deltas(candidate, baseline):
    return {
        key: float(candidate[key]) - float(baseline[key])
        for key in ("reference_top1", "pairwise_accuracy", "mrr")
    }


def _decision(proxy_contract, hybrid_generalization, density, hybrid, nearest, random):
    pooled_delta = _metric_deltas(hybrid["metrics"]["pooled"], nearest["metrics"]["pooled"])
    fold_delta = {
        fold: _metric_deltas(hybrid["metrics"]["by_fold"][fold], nearest["metrics"]["by_fold"][fold])
        for fold in ("1", "2", "3")
    }
    route_delta = {
        route: _metric_deltas(hybrid["metrics"]["by_route"][route], nearest["metrics"]["by_route"][route])
        for route in DECISION_ROUTES
    }
    thresholds = proxy_contract["decision"]
    density_advantage = (
        density["metrics"]["pooled"]["reference_top1"]
        - random["metrics"]["pooled"]["reference_top1"]
    )
    gates = {
        "hybrid_existing_hard_gates": all(hybrid_generalization["hard_gates"].values()),
        "hybrid_no_existing_generalization_flags": not any(hybrid_generalization["flagged_concerns"].values()),
        "pooled_top1_delta_over_nearest_min": pooled_delta["reference_top1"] >= thresholds["pooled_top1_delta_over_nearest_min"],
        "pooled_pairwise_delta_over_nearest_min": pooled_delta["pairwise_accuracy"] >= thresholds["pooled_pairwise_delta_over_nearest_min"],
        "minimum_fold_top1_delta": min(value["reference_top1"] for value in fold_delta.values()) >= thresholds["minimum_fold_top1_delta"],
        "minimum_route_top1_delta": min(value["reference_top1"] for value in route_delta.values()) >= thresholds["minimum_route_top1_delta"],
        "folds_with_positive_top1_delta_min": sum(value["reference_top1"] > 0.0 for value in fold_delta.values()) >= thresholds["folds_with_positive_top1_delta_min"],
        "routes_with_nonnegative_top1_delta_min": sum(value["reference_top1"] >= 0.0 for value in route_delta.values()) >= thresholds["routes_with_nonnegative_top1_delta_min"],
        "density_only_pairwise_accuracy_min": density["metrics"]["pooled"]["pairwise_accuracy"] >= thresholds["density_only_pairwise_accuracy_min"],
        "density_only_top1_advantage_over_random_min": density_advantage >= thresholds["density_only_top1_advantage_over_random_min"],
    }
    nonpositive = pooled_delta["reference_top1"] <= 0.0 or pooled_delta["pairwise_accuracy"] <= 0.0
    if nonpositive or not gates["hybrid_existing_hard_gates"]:
        state = "NO_GO_INDEPENDENT_DENSITY_SIGNAL"
    elif all(gates.values()):
        state = "GO_INDEPENDENT_INCREMENTAL_DENSITY_SIGNAL"
    else:
        state = "HOLD_WEAK_OR_UNSTABLE_INCREMENTAL_SIGNAL"
    return {
        "decision": state, "gates": gates, "pooled_delta_hybrid_minus_nearest": pooled_delta,
        "by_fold_delta_hybrid_minus_nearest": fold_delta,
        "by_route_delta_hybrid_minus_nearest": route_delta,
        "density_only_top1_advantage_over_random": density_advantage,
        "hybrid_generalization": hybrid_generalization,
    }


def _write_report(path, summary):
    d=summary["decision"]; density=summary["density_only"]["metrics"]; nearest=summary["nearest_distance_baseline"]["metrics"]; hybrid=summary["distance_plus_density"]["metrics"]
    lines=["# V22 Proxy-Resistant Continuation Gate Results","",f"Decision: **{d['decision']}**","","This development-only result measures weak-reference compatibility, not biological continuation truth. No assignment or graph mutation occurred.","","## Pooled Comparison","","| Model | Top-1 | Pairwise | MRR |","| --- | ---: | ---: | ---: | ---: |"]
    for name,metrics in [("density only",density["pooled"]),("nearest distance",nearest["pooled"]),("distance plus density",hybrid["pooled"])]:
        lines.append(f"| {name} | {metrics['reference_top1']:.9f} | {metrics['pairwise_accuracy']:.9f} | {metrics['mrr']:.9f} |")
    random_top1=summary["random_within_group"]["metrics"]["pooled"]["reference_top1"]
    lines += ["",f"Random-within-group expected top-1: `{random_top1:.9f}`; density-only advantage: `{d['density_only_top1_advantage_over_random']:+.9f}`.","","## Density-Only Fold And Route Results","","| Stratum | Top-1 | Pairwise | MRR |","| --- | ---: | ---: | ---: | ---: |"]
    for fold in ("1","2","3"):
        metrics=density["by_fold"][fold]
        lines.append(f"| fold {fold} | {metrics['reference_top1']:.9f} | {metrics['pairwise_accuracy']:.9f} | {metrics['mrr']:.9f} |")
    for route in DECISION_ROUTES:
        metrics=density["by_route"][route]
        lines.append(f"| {route} | {metrics['reference_top1']:.9f} | {metrics['pairwise_accuracy']:.9f} | {metrics['mrr']:.9f} |")
    lines += ["","## Incremental Fold And Route Results","","| Stratum | Nearest top-1 | Hybrid top-1 | Delta |","| --- | ---: | ---: | ---: |"]
    for fold in ("1","2","3"):
        lines.append(f"| fold {fold} | {nearest['by_fold'][fold]['reference_top1']:.9f} | {hybrid['by_fold'][fold]['reference_top1']:.9f} | {d['by_fold_delta_hybrid_minus_nearest'][fold]['reference_top1']:+.9f} |")
    for route in DECISION_ROUTES:
        lines.append(f"| {route} | {nearest['by_route'][route]['reference_top1']:.9f} | {hybrid['by_route'][route]['reference_top1']:.9f} | {d['by_route_delta_hybrid_minus_nearest'][route]['reference_top1']:+.9f} |")
    lines += ["","## Frozen Gates",""]
    for name,passed in d["gates"].items(): lines.append(f"- {'PASS' if passed else 'FAIL'}: `{name}`")
    lines += ["","## Boundary","","- Local-maxima is excluded from the decision and remains unproven generalization.","- A GO would authorize only the development joint-assignment shadow.","- `assignment_enabled=false`, `graph_mutated=false`, and `full_199_authorized=false`."]
    path.write_text("\n".join(lines)+"\n",encoding="utf-8")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--contract",type=Path,default=ROOT/"tests/fixtures/v22_proxy_resistant_continuation_gate.json")
    parser.add_argument("--head-contract",type=Path,default=ROOT/"tests/fixtures/v22_continuation_head_preregistration.json")
    parser.add_argument("--feature-contract",type=Path,default=ROOT/"tests/fixtures/v22_continuation_feature_table.json")
    parser.add_argument("--shards",type=Path,default=ROOT/"v22_continuation_feature_shards")
    parser.add_argument("--output",type=Path,default=ROOT/"v22_proxy_resistant_continuation_gate_summary.json")
    parser.add_argument("--group-output",type=Path,default=ROOT/"v22_proxy_resistant_continuation_gate_groups.csv.gz")
    parser.add_argument("--report",type=Path,default=ROOT/"V22_PROXY_RESISTANT_CONTINUATION_GATE_RESULTS.md")
    args=parser.parse_args()
    contract=json.loads(args.contract.read_text(encoding="utf-8-sig")); head=json.loads(args.head_contract.read_text(encoding="utf-8-sig")); feature_contract=json.loads(args.feature_contract.read_text(encoding="utf-8-sig"))
    for path_key,hash_key in [("source_head_contract","source_head_contract_sha256"),("source_head_summary","source_head_summary_sha256"),("source_proxy_audit","source_proxy_audit_sha256")]:
        if _sha256(ROOT/contract[path_key]) != contract[hash_key]: raise RuntimeError(f"Pinned source changed: {path_key}")
    feature_names=list(feature_contract["feature_contract"]["model_feature_allowlist"]); samples=_load_samples(args.shards,feature_names)
    density_names=list(contract["density_ownership_features"]); hybrid_names=list(contract["models"]["distance_plus_density"]["features"])
    density=_fit_oof(samples,feature_names,density_names,head,"density_only")
    hybrid=_fit_oof(samples,feature_names,hybrid_names,head,"distance_plus_density")
    nearest=_fixed_nearest_distance(samples,feature_names,head); random=_random_expectation(samples)
    hybrid_generalization=evaluate_generalization(pooled=hybrid["metrics"]["pooled"],by_fold=hybrid["metrics"]["by_fold"],by_route=hybrid["metrics"]["by_route"],by_fold_route=hybrid["metrics"]["by_fold_route"],contract=head)
    decision=_decision(contract,hybrid_generalization,density,hybrid,nearest,random)
    group_frames=[]
    for model,prefix in [(density,"density"),(hybrid,"hybrid"),(nearest,"nearest")]:
        frame=pd.DataFrame(model.pop("group_rows"))[["reference_id","top1","pairwise_accuracy","rank","mrr"]].rename(columns={name:f"{prefix}_{name}" for name in ["top1","pairwise_accuracy","rank","mrr"]})
        group_frames.append(frame)
    groups=group_frames[0].merge(group_frames[1],on="reference_id",validate="one_to_one").merge(group_frames[2],on="reference_id",validate="one_to_one"); groups.to_csv(args.group_output,index=False,compression="gzip")
    summary={"contract":contract["name"],"contract_sha256":_sha256(args.contract),"density_only":density,"nearest_distance_baseline":nearest,"distance_plus_density":hybrid,"random_within_group":random,"decision":decision,"local_maxima_decision_eligible":False,"assignment_enabled":False,"graph_mutated":False,"full_199_authorized":False,"interpretation_boundary":"weak-reference prediction is not biological validation"}
    args.output.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8"); _write_report(args.report,summary)
    print(json.dumps({"decision":decision["decision"],"density_pooled":density["metrics"]["pooled"],"nearest_pooled":nearest["metrics"]["pooled"],"hybrid_pooled":hybrid["metrics"]["pooled"],"deltas":decision["pooled_delta_hybrid_minus_nearest"],"gates":decision["gates"]},indent=2),flush=True)


if __name__=="__main__": main()

