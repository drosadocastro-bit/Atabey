"""Audit label and crop availability for a pair-conditioned 3D temporal field."""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from atabey.io.zarr_reader import open_competition_array


VOXEL_SCALE_UM = np.asarray((1.625, 0.40625, 0.40625), dtype=float)
HALF_EXTENT_UM = 16.0


def crop_coverage(position_um: np.ndarray, spatial_shape: tuple[int, ...]) -> float:
    domain_high = (np.asarray(spatial_shape, dtype=float) - 1.0) * VOXEL_SCALE_UM
    low = position_um - HALF_EXTENT_UM
    high = position_um + HALF_EXTENT_UM
    overlap = np.maximum(0.0, np.minimum(high, domain_high) - np.maximum(low, 0.0))
    return float(np.prod(overlap / (2.0 * HALF_EXTENT_UM)))


def counts(frame: pd.DataFrame) -> dict:
    return {
        "actions": int(len(frame)),
        "events": int(frame.event_id.nunique()),
        "samples": int(frame.sample_id.nunique()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--peaks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    columns = [
        "action_id", "sample_id", "t", "fold", "event_id", "source_detector",
        "source_link_strategy", "official_label", "parent_peak_id", "child_1_peak_id",
        "child_2_peak_id",
    ]
    actions = pd.concat(
        [pd.read_csv(path, usecols=columns) for path in glob.glob(str(args.shards / "*.csv.gz"))],
        ignore_index=True,
    )
    labeled = actions[actions.official_label.isin(("official_tp", "official_fp"))].copy()
    labeled["family"] = labeled.sample_id.str.split("_").str[0]
    labeled["route"] = labeled.source_detector + "/" + labeled.source_link_strategy
    peaks = pd.read_csv(args.peaks).set_index("peak_id")
    shapes = {
        sample_id: tuple(open_competition_array(args.train_dir / f"{sample_id}.zarr").shape)
        for sample_id in sorted(labeled.sample_id.unique())
    }

    records = []
    for row in labeled.itertuples(index=False):
        peak_ids = (row.parent_peak_id, row.child_1_peak_id, row.child_2_peak_id)
        present = all(peak_id in peaks.index for peak_id in peak_ids)
        frame_valid = False
        positions_valid = False
        coverage = None
        pair_inside_field = False
        if present:
            selected = [peaks.loc[peak_id] for peak_id in peak_ids]
            frame_valid = (
                int(selected[0].t) == int(row.t)
                and int(selected[1].t) == int(row.t) + 1
                and int(selected[2].t) == int(row.t) + 1
                and int(row.t) >= 0
                and int(row.t) + 1 < shapes[row.sample_id][0]
            )
            positions = [np.asarray((item.z_um, item.y_um, item.x_um), dtype=float) for item in selected]
            domain_high = (np.asarray(shapes[row.sample_id][1:], dtype=float) - 1.0) * VOXEL_SCALE_UM
            positions_valid = all(np.all(point >= 0.0) and np.all(point <= domain_high) for point in positions)
            coverage = crop_coverage(positions[0], shapes[row.sample_id][1:])
            pair_inside_field = all(np.max(np.abs(point - positions[0])) <= HALF_EXTENT_UM for point in positions[1:])
        records.append({
            "action_id": row.action_id,
            "sample_id": row.sample_id,
            "fold": int(row.fold),
            "event_id": row.event_id,
            "family": row.family,
            "route": row.route,
            "official_label": row.official_label,
            "peaks_present": present,
            "frame_valid": frame_valid,
            "positions_valid": positions_valid,
            "pair_inside_field": pair_inside_field,
            "unpadded_crop_coverage": coverage,
            "representation_available": bool(present and frame_valid and positions_valid and pair_inside_field),
        })
    audit = pd.DataFrame(records)

    tp = audit[audit.official_label == "official_tp"]
    fp = audit[audit.official_label == "official_fp"]
    availability = {
        "official_tp": float(tp.representation_available.mean()),
        "official_fp": float(fp.representation_available.mean()),
        "tp_crop_coverage": {
            "min": float(tp.unpadded_crop_coverage.min()),
            "median": float(tp.unpadded_crop_coverage.median()),
            "p10": float(tp.unpadded_crop_coverage.quantile(0.10)),
        },
    }
    strata = {}
    for field in ("fold", "family", "route"):
        strata[field] = {
            str(value): {
                "official_tp": counts(group[group.official_label == "official_tp"]),
                "official_fp": counts(group[group.official_label == "official_fp"]),
            }
            for value, group in audit.groupby(field, sort=True)
        }

    folds = sorted(int(value) for value in audit.fold.unique())
    fold_support = {}
    for heldout in folds:
        train = tp[tp.fold != heldout]
        test = tp[tp.fold == heldout]
        fold_support[str(heldout)] = {
            "training": {
                "cfar_events": int(train[train.route == "cfar_sidelobe/bipartite"].event_id.nunique()),
                "44b6_events": int(train[train.family == "44b6"].event_id.nunique()),
                "6bba_events": int(train[train.family == "6bba"].event_id.nunique()),
            },
            "heldout": {
                "cfar_events": int(test[test.route == "cfar_sidelobe/bipartite"].event_id.nunique()),
                "44b6_events": int(test[test.family == "44b6"].event_id.nunique()),
                "6bba_events": int(test[test.family == "6bba"].event_id.nunique()),
            },
        }

    gates = {
        "tp_representation_availability_min": availability["official_tp"] >= 0.99,
        "fp_representation_availability_min": availability["official_fp"] >= 0.99,
        "cfar_positive_samples_min": tp[tp.route == "cfar_sidelobe/bipartite"].sample_id.nunique() >= 6,
        "each_family_positive_samples_min": min(tp.groupby("family").sample_id.nunique()) >= 3,
        "each_fold_training_cfar_events_min": all(item["training"]["cfar_events"] >= 4 for item in fold_support.values()),
        "each_fold_heldout_cfar_events_min": all(item["heldout"]["cfar_events"] >= 2 for item in fold_support.values()),
        "each_fold_training_44b6_events_min": all(item["training"]["44b6_events"] >= 4 for item in fold_support.values()),
        "each_fold_heldout_44b6_events_min": all(item["heldout"]["44b6_events"] >= 2 for item in fold_support.values()),
    }
    decision = "GO_TO_PAIR_FIELD_EXTRACTION" if all(gates.values()) else "NO_GO_CURRENT_E016_PAIR_FIELD_TRAINING"
    summary = {
        "status": "read_only_v23_pair_field_representation_availability",
        "decision": decision,
        "representation": {
            "channels": ["image_t", "image_t_plus_1", "parent_mask", "symmetric_daughter_pair_mask", "crop_coverage_mask"],
            "isotropic_spacing_um": 1.0,
            "half_extent_um": HALF_EXTENT_UM,
            "shape": [33, 33, 33],
            "coordinate_scalar_inputs": False,
        },
        "population": {
            "actions": int(len(actions)),
            "labeled_actions": int(len(audit)),
            "official_tp": counts(tp),
            "official_fp": counts(fp),
        },
        "availability": availability,
        "strata": strata,
        "fold_support": fold_support,
        "gates": gates,
        "model_fitted": False,
        "crops_extracted": False,
        "assignment_enabled": False,
        "graph_mutation": False,
        "full_199_authorized": False,
    }
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# V23 Pair-Conditioned 3D Field Availability Results",
        "",
        f"Decision: **{decision}**.",
        "",
        "The proposed representation is a 33 x 33 x 33 isotropic field centered on the parent with two image frames, symmetric candidate masks, and an explicit crop-coverage mask. No coordinate scalar, model, crop tensor, assignment, or graph edit was created.",
        "",
        f"Representation availability: TP {availability['official_tp']:.1%}; official FP {availability['official_fp']:.1%}. TP unpadded crop coverage min/median/p10: {availability['tp_crop_coverage']['min']:.1%}/{availability['tp_crop_coverage']['median']:.1%}/{availability['tp_crop_coverage']['p10']:.1%}.",
        "",
        "| Held-out fold | Train CFAR | Test CFAR | Train 44b6 | Test 44b6 | Train 6bba | Test 6bba |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for fold, item in fold_support.items():
        lines.append(
            f"| {fold} | {item['training']['cfar_events']} | {item['heldout']['cfar_events']} | "
            f"{item['training']['44b6_events']} | {item['heldout']['44b6_events']} | "
            f"{item['training']['6bba_events']} | {item['heldout']['6bba_events']} |"
        )
    lines += ["", "## Gates", ""]
    for name, passed in gates.items():
        lines.append(f"- {'PASS' if passed else 'FAIL'}: `{name}`")
    lines += [
        "",
        "The image field is technically extractable, but the current E016 labels cannot support honest CFAR and 44b6 generalization. The next allowed step is a CFAR-native official-action availability census over the 66 routed samples, not model training.",
        "",
        "Guardrail: unknown actions remain unknown. This result does not authorize crop extraction at scale, fitting, assignment, graph mutation, or a full-cohort evaluation.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"decision": decision, "availability": availability, "fold_support": fold_support, "gates": gates}, indent=2), flush=True)


if __name__ == "__main__":
    main()
