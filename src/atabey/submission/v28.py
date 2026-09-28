"""V24.3 delivery adapter; policies live in the unchanged tracking modules.

Failure mode addressed: a valid internal graph is not necessarily a complete,
well-formed competition CSV. No scoring, label access or fallback is performed.
"""
from __future__ import annotations

import csv
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import time

from atabey.constants import DEFAULT_VOXEL_SCALE_UM
from atabey.detection.adaptive import choose_settings_for_sample
from atabey.io.zarr_reader import open_competition_array
from atabey.submission.writer import KAGGLE_SUBMISSION_COLUMNS, graph_to_submission_rows
from atabey.tracking.unet_graph import graph_signature, relink_predictor_detections
from atabey.tracking.v24_2_shadow import prune_interior_isolated_detections
from atabey.tracking.v24_3_shadow import prune_interior_short_fragments


def require(condition, message):
    if not condition:
        raise ValueError(message)


def discover_samples(directory: Path) -> list[Path]:
    require(directory.is_dir(), f"Missing sample directory: {directory}")
    samples = sorted(directory.glob("*.zarr"))
    require(bool(samples), "No samples discovered")
    require(all(p.is_dir() for p in samples), "Every sample must be a Zarr directory")
    require(all(p.stem and ',' not in p.stem and '\n' not in p.stem and '\r' not in p.stem for p in samples), "Invalid dataset name")
    return samples


def inspect_sample(path: Path) -> dict:
    import zarr

    root = zarr.open_group(str(path), mode="r")
    array = open_competition_array(path)
    shape = tuple(int(v) for v in array.shape)
    require(len(shape) == 4 and shape[0] >= 2 and min(shape) > 0, "Expected positive TZYX with at least two frames")
    attrs = dict(root.attrs)
    scales = attrs.get("multiscales", [])
    require(len(scales) == 1, "Ambiguous/missing multiscale metadata")
    spec = scales[0]
    axes = spec.get("axes", [])
    require([a.get("name", "").lower() for a in axes] == list("tzyx"), "Expected TZYX axes")
    require(all(a.get("unit") == "micrometer" for a in axes[1:]), "Expected micrometer spatial units")
    datasets = [d for d in spec.get("datasets", []) if d.get("path") == "0"]
    require(len(datasets) == 1, "Missing/ambiguous level 0 transform")
    transforms = datasets[0].get("coordinateTransformations", [])
    require(len(transforms) == 1 and transforms[0].get("type") == "scale", "Unsupported coordinate transform")
    scale = transforms[0].get("scale", [])
    require(len(scale) == 4 and all(math.isfinite(float(x)) and float(x) > 0 for x in scale), "Invalid scale")
    require(tuple(float(x) for x in scale[1:]) == tuple(asdict(DEFAULT_VOXEL_SCALE_UM).values()), "Incompatible physical scale")
    q = attrs.get("image_statistics", {}).get("quantiles", {})
    require(all(k in q for k in ("0.001", "0.999")), "Missing predictor quantiles")
    lo, hi = float(q["0.001"]), float(q["0.999"])
    require(math.isfinite(lo) and math.isfinite(hi) and hi > lo, "Invalid predictor quantiles")
    return {"sample_id": path.stem, "shape": list(shape), "scale": list(scale), "quantiles": {"0.001": lo, "0.999": hi}}


def route_for_sample(path: Path) -> dict:
    start = time.perf_counter()
    profile, settings = choose_settings_for_sample(path)
    # Reference _should_use_cfar_route returns False for components. Thus this
    # predicate is exact without constructing the unused V19 graph/CFAR branch.
    return {"adaptive_detector": settings.detector, "apply_pruning": path.stem.startswith("6bba_") and settings.detector == "components", "profile": asdict(profile), "seconds": time.perf_counter() - start}


def build_graph(sample_id: str, coordinates, apply_pruning: bool):
    start = time.perf_counter()
    graph = relink_predictor_detections(sample_id, coordinates)
    linking_seconds = time.perf_counter() - start
    raw_nodes, raw_edges = len(graph.detections), len(graph.edges)
    start = time.perf_counter()
    if apply_pruning:
        graph = prune_interior_short_fragments(prune_interior_isolated_detections(graph))
    return graph, {"linking_seconds": linking_seconds, "pruning_seconds": time.perf_counter() - start, "raw_nodes": raw_nodes, "raw_edges": raw_edges}


def signature(graph) -> str:
    return hashlib.sha256(repr(graph_signature(graph)).encode("utf-8")).hexdigest()


def export_graph(graph, shape, start_id: int):
    require(bool(graph.detections), "Empty graph cannot represent a required dataset")
    ids = [n.node_id for n in graph.detections]
    require(len(ids) == len(set(ids)), "Duplicate internal node IDs")
    by_id = {n.node_id: n for n in graph.detections}
    rounded = 0
    for n in graph.detections:
        require(n.sample_id == graph.sample_id, "Cross-dataset node")
        raw = (n.t, n.z, n.y, n.x)
        require(all(math.isfinite(v) for v in raw), "Non-finite coordinate")
        require(n.t == int(n.t), "Nonintegral frame")
        require(all(0 <= v < limit for v, limit in zip(raw, shape)), "Coordinate outside source image")
        require(all(0 <= round(v) < limit for v, limit in zip(raw, shape)), "Rounded coordinate outside source image")
        rounded += any(v != round(v) for v in raw[1:])
    seen = set()
    for e in graph.edges:
        require(e.source_id in by_id and e.target_id in by_id, "Missing edge endpoint")
        require(by_id[e.target_id].t == by_id[e.source_id].t + 1, "Non-adjacent edge")
        key = (e.source_id, e.target_id)
        require(key not in seen, "Duplicate edge")
        seen.add(key)
    frame = graph_to_submission_rows(graph, start_id=start_id)
    text = frame.to_csv(index=False, header=False, lineterminator="\n")
    return text, {"sample_id": graph.sample_id, "shape": list(shape), "nodes": len(graph.detections), "edges": len(graph.edges), "rows": len(frame), "rounded_nodes": rounded, "export_rows_sha256": hashlib.sha256(text.encode()).hexdigest(), "graph_signature_sha256": signature(graph)}


def validate_csv(path: Path, records: list[dict]) -> dict:
    """Stream-read and verify each dataset, retaining only one graph's IDs."""
    require(bool(records), "No expected samples")
    require(len({r['sample_id'] for r in records}) == len(records), "Duplicate expected sample")
    expected_id = 0
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream)
        require(next(reader, None) == KAGGLE_SUBMISSION_COLUMNS, "Wrong CSV header")
        for record in records:
            node_times, edges = {}, set()
            digest = hashlib.sha256()
            for index in range(record['rows']):
                row = next(reader, None)
                require(row is not None and len(row) == 10, "Missing/malformed row")
                require(row[1] == record['sample_id'], "Unexpected dataset/order")
                values = [int(row[i]) for i in (0,3,4,5,6,7,8,9)]
                require(all(str(v) == row[i] for v,i in zip(values,(0,3,4,5,6,7,8,9))), "Noncanonical integer")
                rid,nid,t,z,y,x,src,dst = values
                require(rid == expected_id, "Nonconsecutive row ID")
                expected_id += 1
                if row[2] == 'node':
                    require(index < record['nodes'], "Node after edges")
                    nid,t,z,y,x = map(int,row[3:8])
                    require(row[8:] == ['-1','-1'], "Invalid node placeholders")
                    require(nid == len(node_times)+1, "Duplicate/nonsequential node ID")
                    require(all(0 <= v < limit for v,limit in zip((t,z,y,x),record['shape'])), "CSV coordinate outside image")
                    node_times[nid] = t
                elif row[2] == 'edge':
                    require(index >= record['nodes'] and row[3:8] == ['-1']*5, "Invalid edge placeholders/order")
                    src,dst = map(int,row[8:10])
                    require(src in node_times and dst in node_times, "CSV edge endpoint missing")
                    require(node_times[dst] == node_times[src]+1, "CSV edge not adjacent")
                    require((src,dst) not in edges, "Duplicate CSV edge")
                    edges.add((src,dst))
                else:
                    raise ValueError("Invalid row_type")
                digest.update((','.join(row)+'\n').encode())
            require(len(node_times)==record['nodes'] and len(edges)==record['edges'], "Graph count mismatch")
            require(digest.hexdigest()==record['export_rows_sha256'], "CSV differs from intended graph export")
        require(next(reader,None) is None, "Unexpected extra rows")
    return {"status":"VALID", "samples":len(records), "rows":expected_id, "bytes":path.stat().st_size}
