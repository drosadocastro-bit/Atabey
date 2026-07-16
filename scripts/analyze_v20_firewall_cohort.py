from __future__ import annotations

import argparse
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median


VERSION_ORDER = ("V13", "V19", "V20 (Bipartite)")
SAMPLE_RE = re.compile(r"^--- Results for (?P<sample>[^ ]+) ---$")
METRIC_RE = re.compile(
    r"^\s+(?P<version>V13|V19|V20(?: \(Bipartite\))?):\s+"
    r"(?:detector=(?P<detector>\S+)\s+link=(?P<link>\S+)\s+)?"
    r"DivJ=(?P<jaccard>None|[-+0-9.eE]+)\s+"
    r"\(TP:(?P<tp>\d+)\s+FP:(?P<fp>\d+)\s+FN:(?P<fn>\d+)\)\s+"
    r"\|\s+EdgeRecall=(?P<edge>None|[-+0-9.eE]+)"
    r"(?:\s+\|\s+Nodes=(?P<nodes>\d+))?$"
)


@dataclass(frozen=True)
class VersionMetrics:
    detector: str | None
    link_strategy: str | None
    division_jaccard: float | None
    tp: int
    fp: int
    fn: int
    nodes: int | None
    edge_recall: float | None


@dataclass(frozen=True)
class SampleRecord:
    sample_id: str
    versions: dict[str, VersionMetrics]


@dataclass(frozen=True)
class ClassifiedSample:
    sample: SampleRecord
    bucket: str
    firewall_active: bool
    high_residual_fp: bool
    meaningful_fp_reduction: bool
    edge_delta_vs_v13: float | None
    edge_delta_vs_v19: float | None


def _parse_float(value: str) -> float | None:
    if value == "None":
        return None
    return float(value)


def parse_log(path: Path) -> list[SampleRecord]:
    records: dict[str, dict[str, VersionMetrics]] = {}
    current_sample: str | None = None

    for raw_line in path.read_text(errors="replace").splitlines():
        line = raw_line.rstrip()
        sample_match = SAMPLE_RE.match(line)
        if sample_match:
            current_sample = sample_match.group("sample")
            records.setdefault(current_sample, {})
            continue

        metric_match = METRIC_RE.match(line)
        if metric_match and current_sample:
            version = metric_match.group("version")
            records[current_sample][version] = VersionMetrics(
                detector=metric_match.group("detector"),
                link_strategy=metric_match.group("link"),
                division_jaccard=_parse_float(metric_match.group("jaccard")),
                tp=int(metric_match.group("tp")),
                fp=int(metric_match.group("fp")),
                fn=int(metric_match.group("fn")),
                nodes=int(metric_match.group("nodes")) if metric_match.group("nodes") else None,
                edge_recall=_parse_float(metric_match.group("edge")),
            )

    parsed = [
        SampleRecord(sample_id=sample_id, versions=versions)
        for sample_id, versions in sorted(records.items())
        if any(version in versions for version in VERSION_ORDER)
    ]
    return parsed


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower)


def dist(values: list[float]) -> dict[str, float | int | None]:
    clean = [value for value in values if value is not None]
    if not clean:
        return {"n": 0, "mean": None, "median": None, "p10": None, "p90": None}
    return {
        "n": len(clean),
        "mean": mean(clean),
        "median": median(clean),
        "p10": percentile(clean, 0.10),
        "p90": percentile(clean, 0.90),
    }


def fmt(value: float | int | None, digits: int = 4) -> str:
    if value is None:
        return "NA"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def get(record: SampleRecord, version: str) -> VersionMetrics | None:
    return record.versions.get(version)


def is_firewall_active(record: SampleRecord) -> bool:
    v20 = get(record, "V20 (Bipartite)")
    return bool(v20 and v20.detector == "v20_firewall" and v20.link_strategy == "bipartite")


def classify(record: SampleRecord) -> ClassifiedSample:
    v13 = get(record, "V13")
    v19 = get(record, "V19")
    v20 = get(record, "V20 (Bipartite)")
    if not v20:
        return ClassifiedSample(record, "missing_v20", False, False, False, None, None)

    active = is_firewall_active(record)
    edge_delta_v13 = None
    edge_delta_v19 = None
    if v13 and v13.edge_recall is not None and v20.edge_recall is not None:
        edge_delta_v13 = v20.edge_recall - v13.edge_recall
    if v19 and v19.edge_recall is not None and v20.edge_recall is not None:
        edge_delta_v19 = v20.edge_recall - v19.edge_recall

    high_residual = v20.fp >= 100
    near_expected = v20.fp <= 5
    v19_fp = v19.fp if v19 else 0
    fp_reduction = v19_fp - v20.fp
    reduction_ratio = (fp_reduction / v19_fp) if v19_fp > 0 else 0.0
    meaningful_reduction = fp_reduction >= 20 and reduction_ratio >= 0.50

    edge_baseline = max(
        [m.edge_recall for m in (v13, v19) if m and m.edge_recall is not None],
        default=None,
    )
    edge_ok = edge_baseline is None or (v20.edge_recall is not None and v20.edge_recall >= edge_baseline - 1e-12)

    if not active:
        bucket = "no_cfar_or_firewall_not_applicable"
    elif edge_ok and near_expected:
        bucket = "clean_win"
    elif high_residual:
        bucket = "firewall_insufficient_high_residual"
    elif meaningful_reduction:
        bucket = "firewall_working_fp_reduction"
    elif edge_delta_v13 is not None and edge_delta_v13 < -1e-12:
        bucket = "edge_recall_regression"
    else:
        bucket = "firewall_active_other"

    return ClassifiedSample(
        sample=record,
        bucket=bucket,
        firewall_active=active,
        high_residual_fp=high_residual,
        meaningful_fp_reduction=meaningful_reduction,
        edge_delta_vs_v13=edge_delta_v13,
        edge_delta_vs_v19=edge_delta_v19,
    )


def version_distributions(records: list[SampleRecord]) -> dict[str, dict[str, dict[str, float | int | None]]]:
    output: dict[str, dict[str, dict[str, float | int | None]]] = {}
    for version in VERSION_ORDER:
        metrics = [get(record, version) for record in records if get(record, version)]
        output[version] = {
            "division_jaccard": dist([m.division_jaccard for m in metrics if m]),
            "edge_recall": dist([m.edge_recall for m in metrics if m]),
            "division_fp": dist([float(m.fp) for m in metrics if m]),
        }
    return output


def group_stats(values: list[float]) -> str:
    summary = dist(values)
    return (
        f"n={summary['n']}, mean={fmt(summary['mean'])}, median={fmt(summary['median'])}, "
        f"p10={fmt(summary['p10'])}, p90={fmt(summary['p90'])}"
    )


def edge_breakdown(classified: list[ClassifiedSample], baseline: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    attr = "edge_delta_vs_v13" if baseline == "V13" else "edge_delta_vs_v19"
    for item in classified:
        delta = getattr(item, attr)
        if delta is None:
            counts["missing"] += 1
        elif delta > 1e-12:
            counts["improved"] += 1
        elif delta < -1e-12:
            counts["regressed"] += 1
        else:
            counts["flat"] += 1
    return counts


def sample_prefix(sample_id: str) -> str:
    return sample_id.split("_", 1)[0]


def recommendation(classified: list[ClassifiedSample]) -> str:
    active = [item for item in classified if item.firewall_active]
    if not active:
        return "NO-GO: no samples confirmed the v20_firewall|bipartite route, so firewall behavior was not measured."

    v20_metrics = [get(item.sample, "V20 (Bipartite)") for item in active]
    total_tp = sum(metric.tp for metric in v20_metrics if metric)
    high_rate = sum(item.high_residual_fp for item in active) / len(active)
    edge_counts = edge_breakdown(classified, "V13")
    reg_rate = edge_counts["regressed"] / max(1, len(classified) - edge_counts["missing"])

    if total_tp == 0 and high_rate > 0.10:
        return (
            "NO-GO for treating the current firewall as a division-scoring improvement: "
            "it produced no confirmed division TP signal while leaving high-FP residuals in a meaningful share of active samples."
        )
    if high_rate > 0.20:
        return (
            "NO-GO / redesign recommended: high residual FP is common among firewall-active samples, "
            "which points beyond small threshold cleanup."
        )
    if reg_rate > 0.10:
        return (
            "NO-GO for submission unless edge recall is protected: V20 regresses Edge Recall on more than 10% of measurable samples."
        )
    return (
        "CONDITIONAL GO for further evaluation: aggregate edge recall is not broadly harmed and high-FP residuals are bounded, "
        "but division TP signal should still be checked before claiming division quality."
    )


def write_report(records: list[SampleRecord], output_path: Path, source_log: Path) -> None:
    classified = [classify(record) for record in records]
    distributions = version_distributions(records)
    bucket_counts = Counter(item.bucket for item in classified)
    route_counts: dict[str, Counter[str]] = {version: Counter() for version in VERSION_ORDER}

    for record in records:
        for version in VERSION_ORDER:
            metric = get(record, version)
            if not metric:
                continue
            route_counts[version][f"{metric.detector}|{metric.link_strategy}"] += 1

    v20_records = [item for item in classified if get(item.sample, "V20 (Bipartite)")]
    active = [item for item in classified if item.firewall_active]
    high = [item for item in active if item.high_residual_fp]
    near_expected = [item for item in active if get(item.sample, "V20 (Bipartite)").fp <= 5]
    mid_fp = [item for item in active if 6 <= get(item.sample, "V20 (Bipartite)").fp < 100]

    lines: list[str] = []
    lines.append("# V20 Firewall Cohort Analysis")
    lines.append("")
    lines.append("Guardrail: this report is pure measurement and classification of the frozen V20 firewall ruleset. No thresholds were tuned.")
    lines.append("")
    lines.append(f"Source log: `{source_log}`")
    lines.append(f"Parsed samples: {len(records)}")
    lines.append("")

    lines.append("## Aggregate Distributions")
    lines.append("")
    lines.append("| Version | Metric | n | mean | median | p10 | p90 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for version in VERSION_ORDER:
        for metric_name, summary in distributions[version].items():
            lines.append(
                f"| {version} | {metric_name} | {summary['n']} | {fmt(summary['mean'])} | "
                f"{fmt(summary['median'])} | {fmt(summary['p10'])} | {fmt(summary['p90'])} |"
            )
    lines.append("")

    lines.append("## V20 FP-Per-Sample Distribution")
    lines.append("")
    v20_fps = [float(get(item.sample, "V20 (Bipartite)").fp) for item in v20_records]
    lines.append(f"All parsed V20 samples: {group_stats(v20_fps)}")
    active_fps = [float(get(item.sample, "V20 (Bipartite)").fp) for item in active]
    lines.append(f"Firewall-active samples only: {group_stats(active_fps)}")
    lines.append(f"Near expected calibration band, FP 0-5: {len(near_expected)} / {len(active)} active samples")
    lines.append(f"Intermediate residual, FP 6-99: {len(mid_fp)} / {len(active)} active samples")
    lines.append(f"High residual outliers, FP >=100: {len(high)} / {len(active)} active samples")
    lines.append("")

    lines.append("## Behavior Buckets")
    lines.append("")
    lines.append("Primary buckets are mutually exclusive. High residual FP and meaningful FP reduction are also tracked separately because they can overlap.")
    lines.append("")
    lines.append("| Bucket | Count | Percent |")
    lines.append("|---|---:|---:|")
    for bucket, count in bucket_counts.most_common():
        pct = (count / len(classified) * 100.0) if classified else 0.0
        lines.append(f"| {bucket} | {count} | {pct:.1f}% |")
    lines.append("")
    lines.append(f"Meaningful V19->V20 FP reduction among firewall-active samples: {sum(item.meaningful_fp_reduction for item in active)} / {len(active)}")
    lines.append(f"High residual FP among firewall-active samples: {len(high)} / {len(active)}")
    lines.append("")

    lines.append("## Route Confirmation")
    lines.append("")
    for version in VERSION_ORDER:
        lines.append(f"### {version}")
        for route, count in route_counts[version].most_common():
            lines.append(f"- `{route}`: {count}")
        lines.append("")

    lines.append("## Edge Recall Net Impact")
    lines.append("")
    for baseline in ("V13", "V19"):
        counts = edge_breakdown(classified, baseline)
        lines.append(
            f"V20 vs {baseline}: improved={counts['improved']}, flat={counts['flat']}, "
            f"regressed={counts['regressed']}, missing={counts['missing']}"
        )
    v13_deltas = [item.edge_delta_vs_v13 for item in classified if item.edge_delta_vs_v13 is not None]
    v19_deltas = [item.edge_delta_vs_v19 for item in classified if item.edge_delta_vs_v19 is not None]
    lines.append(f"V20-V13 Edge Recall delta distribution: {group_stats(v13_deltas)}")
    lines.append(f"V20-V19 Edge Recall delta distribution: {group_stats(v19_deltas)}")
    lines.append("")

    lines.append("## Division TP Signal")
    lines.append("")
    for version in VERSION_ORDER:
        metrics = [get(record, version) for record in records if get(record, version)]
        total_tp = sum(metric.tp for metric in metrics if metric)
        tp_samples = sum(1 for metric in metrics if metric and metric.tp > 0)
        total_fp = sum(metric.fp for metric in metrics if metric)
        total_fn = sum(metric.fn for metric in metrics if metric)
        lines.append(f"- {version}: total TP={total_tp}, samples with TP>0={tp_samples}, total FP={total_fp}, total FN={total_fn}")
    lines.append("")

    lines.append("## High-FP Outlier Correlates")
    lines.append("")
    prefix_counts = Counter(sample_prefix(item.sample.sample_id) for item in active)
    high_prefix_counts = Counter(sample_prefix(item.sample.sample_id) for item in high)
    lines.append("### Cohort Prefix")
    lines.append("| Prefix | Active samples | High-FP samples | High-FP rate |")
    lines.append("|---|---:|---:|---:|")
    for prefix in sorted(prefix_counts):
        active_count = prefix_counts[prefix]
        high_count = high_prefix_counts[prefix]
        rate = high_count / active_count * 100.0 if active_count else 0.0
        lines.append(f"| {prefix} | {active_count} | {high_count} | {rate:.1f}% |")
    lines.append("")

    lines.append("### Density Proxies From Log Metrics")
    lines.append("")
    has_nodes = any((get(item.sample, "V20 (Bipartite)") and get(item.sample, "V20 (Bipartite)").nodes is not None) for item in active)
    if has_nodes:
        lines.append("This log includes per-sample predicted node counts, so V20 nodes are included as a density proxy. Edge counts and raw image density are not present in the log.")
    else:
        lines.append("The current log format does not contain per-sample raw density, node count, or edge count. This section therefore uses cohort prefix and V19/V20 division FP as available noise-density proxies. Future logs from the updated audit script include per-sample `Nodes=...`.")
    for label, subset in (("Firewall active", active), ("High residual FP", high)):
        v19_fp = [float(get(item.sample, "V19").fp) for item in subset if get(item.sample, "V19")]
        v20_fp = [float(get(item.sample, "V20 (Bipartite)").fp) for item in subset if get(item.sample, "V20 (Bipartite)")]
        v20_nodes = [float(get(item.sample, "V20 (Bipartite)").nodes) for item in subset if get(item.sample, "V20 (Bipartite)") and get(item.sample, "V20 (Bipartite)").nodes is not None]
        lines.append(f"- {label} V19 division FP: {group_stats(v19_fp)}")
        lines.append(f"- {label} V20 division FP: {group_stats(v20_fp)}")
        if has_nodes:
            lines.append(f"- {label} V20 predicted nodes: {group_stats(v20_nodes)}")
    lines.append("")

    lines.append("### Top V20 Residual-FP Samples")
    lines.append("")
    lines.append("| Sample | Bucket | Prefix | V19 FP | V20 FP | V20 Edge Recall | V20 route |")
    lines.append("|---|---|---|---:|---:|---:|---|")
    sorted_by_fp = sorted(
        v20_records,
        key=lambda item: get(item.sample, "V20 (Bipartite)").fp if get(item.sample, "V20 (Bipartite)") else -1,
        reverse=True,
    )
    for item in sorted_by_fp[:25]:
        v19 = get(item.sample, "V19")
        v20 = get(item.sample, "V20 (Bipartite)")
        route = f"{v20.detector}|{v20.link_strategy}" if v20 else "missing"
        lines.append(
            f"| {item.sample.sample_id} | {item.bucket} | {sample_prefix(item.sample.sample_id)} | "
            f"{v19.fp if v19 else 'NA'} | {v20.fp if v20 else 'NA'} | "
            f"{fmt(v20.edge_recall if v20 else None)} | `{route}` |"
        )
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    lines.append(recommendation(classified))
    lines.append("")

    output_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze V20 bipartite/firewall cohort audit logs.")
    parser.add_argument("log_path", type=Path, help="Path to v20_bipartite_firewall_199.log")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("V20_FIREWALL_COHORT_ANALYSIS.md"),
        help="Markdown report path",
    )
    args = parser.parse_args()

    records = parse_log(args.log_path)
    if not records:
        raise SystemExit(f"No per-sample result blocks parsed from {args.log_path}")
    write_report(records, args.output, args.log_path)
    print(f"Wrote {args.output} from {len(records)} parsed samples")


if __name__ == "__main__":
    main()

