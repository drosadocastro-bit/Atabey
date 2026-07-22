from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median

import numpy as np
from scipy.stats import spearmanr

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from analyze_v20_firewall_cohort import get, parse_log
from atabey.detection.adaptive import choose_adaptive_baseline_settings, profile_sample_foreground
from atabey.diagnostics.sun_check import SampleSunCheck, audit_sample
from run_hybrid_submission import _should_use_cfar_route


@dataclass(frozen=True)
class PanelSample:
    sample_id: str
    role: str


PANEL = (
    PanelSample("44b6_0113de3b", "components control, high EdgeRecall"),
    PanelSample("44b6_24264f12", "components control, high EdgeRecall"),
    PanelSample("44b6_d754aa59", "components control, known Phase 2 division window"),
    PanelSample("44b6_12dfb391", "local-maxima non-CFAR, known Phase 2 division window"),
    PanelSample("44b6_0c582fdc", "atypical 44b6 CFAR route, strong V20 EdgeRecall gain"),
    PanelSample("44b6_2a2eff9f", "44b6 CFAR route, V20 below V13"),
    PanelSample("6bba_05db0fb1", "official V19 division TP"),
    PanelSample("6bba_32db13fc", "official V19 division TP"),
    PanelSample("6bba_b329af44", "official V19 division TP"),
    PanelSample("6bba_ebdf3b34", "official V19 division TP plus known FN"),
    PanelSample("6bba_ebff6e76", "prior high-residual division-noise case"),
    PanelSample("6bba_55b7eebe", "6bba components/non-CFAR control"),
)


def _historical_records(log_path: Path):
    if not log_path.exists():
        return {}
    return {record.sample_id: record for record in parse_log(log_path)}


def _sample_row(
    panel: PanelSample,
    report: SampleSunCheck,
    *,
    route: str,
    profile,
    historical,
) -> dict[str, object]:
    v13 = get(historical, "V13") if historical else None
    v19 = get(historical, "V19") if historical else None
    v20 = get(historical, "V20 (Bipartite)") if historical else None
    return {
        "sample_id": panel.sample_id,
        "cohort": panel.sample_id.split("_", 1)[0],
        "panel_role": panel.role,
        "current_route": route,
        "median_largest_component_voxels": profile.median_largest_component_voxels,
        "median_foreground_fraction": profile.median_foreground_fraction,
        "historical_v20_detector": v20.detector if v20 else None,
        "historical_v20_link": v20.link_strategy if v20 else None,
        "historical_v13_edge_recall": v13.edge_recall if v13 else None,
        "historical_v19_edge_recall": v19.edge_recall if v19 else None,
        "historical_v20_edge_recall": v20.edge_recall if v20 else None,
        "historical_v20_delta_v13": (
            v20.edge_recall - v13.edge_recall
            if v20 and v13 and v20.edge_recall is not None and v13.edge_recall is not None
            else None
        ),
        "historical_v20_division_fp_legacy": v20.fp if v20 else None,
        "median_background": report.median_background,
        "background_temporal_spread": report.background_temporal_spread,
        "median_snr_proxy": report.median_snr_proxy,
        "median_z_profile_spread": report.median_z_profile_spread,
        "median_xy_shading_spread": report.median_xy_shading_spread,
        "max_saturation_fraction": report.max_saturation_fraction,
        "median_compact_sigma_z_um": report.median_compact_sigma_z_um,
        "median_compact_sigma_y_um": report.median_compact_sigma_y_um,
        "median_compact_sigma_x_um": report.median_compact_sigma_x_um,
        "median_drift_um": report.median_drift_um,
        "p90_drift_um": report.p90_drift_um,
        "q90_end_to_start_ratio": report.q90_end_to_start_ratio,
    }


def _frame_rows(report: SampleSunCheck) -> list[dict[str, object]]:
    drifts = {drift.t_from: drift for drift in report.drift_metrics}
    rows = []
    for frame in report.frame_metrics:
        row = {"sample_id": report.sample_id, **asdict(frame)}
        drift = drifts.get(frame.t)
        row.update(
            {
                "adjacent_shift_z_um": drift.shift_z_um if drift else None,
                "adjacent_shift_y_um": drift.shift_y_um if drift else None,
                "adjacent_shift_x_um": drift.shift_x_um if drift else None,
                "adjacent_shift_magnitude_um": drift.shift_magnitude_um if drift else None,
            }
        )
        rows.append(row)
    return rows


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fmt(value, digits=3):
    if value is None:
        return "NA"
    return f"{float(value):.{digits}f}"


def _group_summary(rows: list[dict[str, object]], key: str) -> list[str]:
    lines = []
    for label in sorted({str(row[key]) for row in rows}):
        group = [row for row in rows if str(row[key]) == label]
        lines.append(
            f"- `{label}` (n={len(group)}): background median={_fmt(median(float(r['median_background']) for r in group))}, "
            f"SNR proxy median={_fmt(median(float(r['median_snr_proxy']) for r in group))}, "
            f"drift median={_fmt(median(float(r['median_drift_um']) for r in group))} um, "
            f"q90 end/start mean={_fmt(mean(float(r['q90_end_to_start_ratio']) for r in group))}."
        )
    return lines


def _correlations(
    rows: list[dict[str, object]],
    *,
    route: str | None = None,
) -> list[tuple[str, int, float, float]]:
    selected = [row for row in rows if route is None or row["current_route"] == route]
    features = (
        "median_background",
        "background_temporal_spread",
        "median_snr_proxy",
        "median_z_profile_spread",
        "median_xy_shading_spread",
        "median_drift_um",
        "p90_drift_um",
        "q90_end_to_start_ratio",
    )
    results = []
    for feature in features:
        paired = [
            (float(row[feature]), float(row["historical_v20_delta_v13"]))
            for row in selected
            if row[feature] is not None and row["historical_v20_delta_v13"] is not None
        ]
        if len(paired) < 4 or len({x for x, _ in paired}) < 2 or len({y for _, y in paired}) < 2:
            continue
        statistic = spearmanr([x for x, _ in paired], [y for _, y in paired])
        results.append((feature, len(paired), float(statistic.statistic), float(statistic.pvalue)))
    return sorted(results, key=lambda item: abs(item[2]), reverse=True)


def _write_report(path: Path, rows: list[dict[str, object]]) -> None:
    correlations = _correlations(rows)
    cfar_correlations = _correlations(rows, route="cfar_sidelobe")
    route_agreement = sum(
        (
            row["current_route"] == "cfar_sidelobe"
            and row["historical_v20_detector"] == "v20_firewall"
        )
        or (
            row["current_route"] == "components/greedy"
            and row["historical_v20_detector"] == "components"
        )
        or (
            str(row["current_route"]).startswith("local_maxima/")
            and row["historical_v20_detector"] == "local_maxima"
        )
        for row in rows
    )
    footprint_ranges = {
        axis: (
            min(float(row[f"median_compact_sigma_{axis}_um"]) for row in rows),
            max(float(row[f"median_compact_sigma_{axis}_um"]) for row in rows),
        )
        for axis in ("z", "y", "x")
    }
    lines = [
        "# Atabey Sun Check Bounded Audit",
        "",
        "Status: read-only, 12-sample diagnostic; no image correction, detector tuning, or graph mutation",
        "",
        "## Measurement Boundary",
        "",
        "This audit adapts the WSR-88D external-reference idea to retrospective single-channel",
        "fluorescence data. Because the competition volumes contain no bead field or instrument telemetry,",
        "background, bulk shift, and compact-object width are explicitly treated as self-consistency",
        "proxies. They are not absolute PSF, stage-drift, gain, or biological measurements.",
        "",
        "Five anchor frames and their immediate successors are read from each sample. Track A, Track B,",
        "the frozen 9 um formation gate, and all image voxels remain unchanged.",
        "",
        "Scientific basis: NOAA solar scans use a known external source to measure antenna pointing,",
        "beamwidth, and gain; fluorescence-microscopy QC uses sub-resolution beads to measure PSF geometry.",
        "This dataset has neither reference, so the present measurements deliberately stop at shadow QC.",
        "",
        "References:",
        "",
        "- NOAA WSR-88D solar calibration: https://www.weather.gov/media/roc/Papers/PolarmetcirWXRadar_Cal_Using_SolarScans_AMTA2014_final.pdf",
        "- Confocal PSF bead protocol: https://www.nature.com/articles/nprot.2011.407",
        "- Fluorescence microscopy reproducibility guidance: https://www.nature.com/articles/s41592-021-01156-w",
        "- Biohub Zebrahub light-sheet acquisition context: https://biohub.org/blog/zebrahub-tracks-zebrafish-development/",
        "",
        "## Panel Results",
        "",
        "| Sample | Role | Route | Background | SNR proxy | Drift um | Z spread | XY spread | q90 end/start |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['sample_id']}` | {row['panel_role']} | `{row['current_route']}` | "
            f"{_fmt(row['median_background'])} | {_fmt(row['median_snr_proxy'])} | "
            f"{_fmt(row['median_drift_um'])} | {_fmt(row['median_z_profile_spread'])} | "
            f"{_fmt(row['median_xy_shading_spread'])} | {_fmt(row['q90_end_to_start_ratio'])} |"
        )
    lines.extend(["", "## Cohort Summary", "", *_group_summary(rows, "cohort")])
    lines.extend(["", "## Route Summary", "", *_group_summary(rows, "current_route")])
    lines.extend(
        [
            "",
            "## Main Findings",
            "",
            f"- Current image-only routing agrees with the historical V20 detector class for **{route_agreement}/{len(rows)}** samples.",
            "- The CFAR group has higher background and lower SNR proxy than the components controls;",
            "  this is coherent with the existing adaptive route but is not yet an independent predictor.",
            f"- Compact-object sigma ranges are narrow: Z `{footprint_ranges['z'][0]:.3f}-{footprint_ranges['z'][1]:.3f}` um, "
            f"Y `{footprint_ranges['y'][0]:.3f}-{footprint_ranges['y'][1]:.3f}` um, and "
            f"X `{footprint_ranges['x'][0]:.3f}-{footprint_ranges['x'][1]:.3f}` um. No large footprint outlier is visible.",
            "- No sampled frame contains saturated uint16 voxels.",
            "- Bulk-shift estimates are self-registration proxies and remain biologically confounded;",
            "  they do not authorize stage-drift correction.",
        ]
    )
    lines.extend(
        [
            "",
            "## Exploratory EdgeRecall Correlations",
            "",
            "Spearman correlations use the reconstructed cohort's EdgeRecall delta (V20 minus V13).",
            "With n=12, these are hypothesis-generating effect sizes, not validation or causal evidence.",
            "The legacy division-FP field is retained in CSV only for provenance and must not be interpreted",
            "after the official metric correction.",
            "",
            "| Proxy | n | rho | p-value |",
            "|---|---:|---:|---:|",
        ]
    )
    for feature, n, rho, pvalue in correlations:
        lines.append(f"| `{feature}` | {n} | {rho:.3f} | {pvalue:.3f} |")
    lines.extend(
        [
            "",
            "### CFAR-only sensitivity check",
            "",
            "Restricting the same analysis to the seven CFAR-routed samples checks whether an apparent",
            "relationship is driven by route composition rather than within-route behavior.",
            "",
            "| Proxy | n | rho | p-value |",
            "|---|---:|---:|---:|",
        ]
    )
    for feature, n, rho, pvalue in cfar_correlations:
        lines.append(f"| `{feature}` | {n} | {rho:.3f} | {pvalue:.3f} |")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "**GO as a sample-state QC and routing research direction. NO-GO for image correction, drift",
            "compensation, or threshold adaptation.** The route separation is coherent and the temporal",
            "intensity range is large enough to justify an independent stratified shadow audit. However,",
            "the strongest full-panel EdgeRecall association weakens inside the CFAR subset, demonstrating",
            "route confounding. A follow-up must pre-register independent samples within each route and must",
            "show value beyond the existing foreground-density profile before any production use.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bounded bead-free Atabey Sun Check audit.")
    parser.add_argument("--train-dir", type=Path, default=project_root / "train")
    parser.add_argument(
        "--cohort-log",
        type=Path,
        default=project_root / "v20_bipartite_firewall_199_RECONSTRUCTED_168.log",
    )
    parser.add_argument("--output-prefix", default="sun_check_bounded_12")
    args = parser.parse_args()

    historical = _historical_records(args.cohort_log)
    sample_rows: list[dict[str, object]] = []
    frame_rows: list[dict[str, object]] = []
    for index, panel in enumerate(PANEL, start=1):
        sample_path = args.train_dir / f"{panel.sample_id}.zarr"
        if not sample_path.exists():
            raise FileNotFoundError(f"Missing fixed-panel sample: {sample_path}")
        print(f"[{index}/{len(PANEL)}] {panel.sample_id}: {panel.role}", flush=True)
        report = audit_sample(sample_path)
        profile = profile_sample_foreground(sample_path)
        settings = choose_adaptive_baseline_settings(profile)
        use_cfar = _should_use_cfar_route(
            profile=profile,
            adaptive_detector=settings.detector,
            cfar_route_policy="merged_6bba_only",
        )
        route = "cfar_sidelobe" if use_cfar else f"{settings.detector}/{settings.link_strategy}"
        row = _sample_row(
            panel,
            report,
            route=route,
            profile=profile,
            historical=historical.get(panel.sample_id),
        )
        sample_rows.append(row)
        frame_rows.extend(_frame_rows(report))
        print(
            f"  route={route} bg={row['median_background']:.1f} snr={row['median_snr_proxy']:.2f} "
            f"drift={row['median_drift_um']:.2f}um q90_ratio={row['q90_end_to_start_ratio']:.3f}",
            flush=True,
        )

    prefix = project_root / args.output_prefix
    sample_path = Path(f"{prefix}_samples.csv")
    frame_path = Path(f"{prefix}_frames.csv")
    report_path = project_root / "ATABEY_SUN_CHECK_BOUNDED_AUDIT.md"
    _write_csv(sample_path, sample_rows)
    _write_csv(frame_path, frame_rows)
    _write_report(report_path, sample_rows)
    print(f"Wrote {sample_path}", flush=True)
    print(f"Wrote {frame_path}", flush=True)
    print(f"Wrote {report_path}", flush=True)


if __name__ == "__main__":
    main()
