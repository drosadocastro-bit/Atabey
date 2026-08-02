from __future__ import annotations

import gzip
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np


TIE_TOLERANCE = 1e-12


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl_gzip(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


@dataclass(frozen=True)
class LockedPairFieldData:
    root: Path
    actions: tuple[dict, ...]
    events: tuple[dict, ...]
    parents: tuple[dict, ...]
    parent_tensors: np.ndarray
    parent_index: dict[str, int]


@dataclass(frozen=True)
class PairwiseFit:
    coefficients: np.ndarray
    converged: bool
    iterations: int
    objective: float


def fit_pairwise_logistic(
    differences: np.ndarray,
    weights: np.ndarray,
    *,
    c: float,
    max_iterations: int = 100,
) -> PairwiseFit:
    """Fit an L2 pairwise logistic utility with all preferences oriented +1."""

    from scipy.optimize import minimize
    from scipy.special import expit

    x = np.asarray(differences, dtype=np.float64)
    pair_weights = np.asarray(weights, dtype=np.float64)
    if x.ndim != 2 or pair_weights.shape != (x.shape[0],):
        raise ValueError("Pair differences and weights have incompatible shapes")
    if x.shape[0] == 0:
        raise ValueError("At least one preference pair is required")
    if c <= 0.0:
        raise ValueError("c must be positive")
    if np.any(pair_weights < 0.0) or not np.all(np.isfinite(pair_weights)):
        raise ValueError("Pair weights must be finite and non-negative")
    weight_sum = float(pair_weights.sum())
    if weight_sum <= 0.0:
        raise ValueError("Pair weights must have positive total mass")
    normalized = pair_weights / weight_sum

    def objective(coefficients: np.ndarray) -> tuple[float, np.ndarray]:
        margins = x @ coefficients
        losses = np.logaddexp(0.0, -margins)
        value = float(np.dot(normalized, losses))
        value += 0.5 * float(np.dot(coefficients, coefficients)) / float(c)
        derivative = -expit(-margins) * normalized
        gradient = x.T @ derivative + coefficients / float(c)
        return value, np.asarray(gradient, dtype=np.float64)

    result = minimize(
        objective,
        np.zeros(x.shape[1], dtype=np.float64),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": int(max_iterations), "ftol": 1e-10, "gtol": 1e-7},
    )
    return PairwiseFit(
        coefficients=np.asarray(result.x, dtype=np.float64),
        converged=bool(result.success),
        iterations=int(result.nit),
        objective=float(result.fun),
    )

def load_locked_pair_field_data(root: Path) -> LockedPairFieldData:
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not manifest["all_parent_tensors_valid"]:
        raise ValueError("Locked parent-tensor manifest is not valid")
    for filename, key in (
        ("actions.jsonl.gz", "actions_sha256"),
        ("events.jsonl.gz", "events_sha256"),
        ("parents.json", "parents_sha256"),
    ):
        if file_sha256(root / filename) != manifest[key]:
            raise ValueError(f"Locked manifest hash mismatch: {filename}")

    actions = tuple(_read_jsonl_gzip(root / "actions.jsonl.gz"))
    events = tuple(_read_jsonl_gzip(root / "events.jsonl.gz"))
    parents = tuple(json.loads((root / "parents.json").read_text(encoding="utf-8")))
    if (len(actions), len(events), len(parents)) != (
        manifest["actions"], manifest["events"], manifest["parent_fields"]
    ):
        raise ValueError("Locked manifest count mismatch")

    tensors = []
    for row in parents:
        path = root / row["relative_path"]
        if file_sha256(path) != row["file_sha256"]:
            raise ValueError(f"Parent tensor file hash mismatch: {path.name}")
        tensor = np.ascontiguousarray(np.load(path, allow_pickle=False), dtype=np.float32)
        digest = hashlib.sha256(tensor.tobytes(order="C")).hexdigest()
        if digest != row["tensor_sha256"]:
            raise ValueError(f"Parent tensor content hash mismatch: {path.name}")
        if tensor.shape != (4, 33, 33, 33):
            raise ValueError(f"Unexpected parent tensor shape: {tensor.shape}")
        tensors.append(tensor)

    parent_index = {row["cache_key"]: index for index, row in enumerate(parents)}
    if len(parent_index) != len(parents):
        raise ValueError("Duplicate parent cache key")
    if any(row["parent_cache_key"] not in parent_index for row in actions):
        raise ValueError("Action references an unknown parent tensor")
    return LockedPairFieldData(
        root=root,
        actions=actions,
        events=events,
        parents=parents,
        parent_tensors=np.stack(tensors),
        parent_index=parent_index,
    )


def model_parameter_count(model) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def build_pair_field_ranker():
    import torch.nn as nn

    class PairFieldRanker(nn.Module):
        def __init__(self):
            super().__init__()
            channels = (5, 8, 12, 16, 24)
            blocks = []
            for in_channels, out_channels, stride in zip(
                channels[:-1], channels[1:], (1, 2, 2, 2)
            ):
                blocks.extend(
                    (
                        nn.Conv3d(in_channels, out_channels, 3, stride, 1, bias=False),
                        nn.GroupNorm(4, out_channels),
                        nn.SiLU(),
                    )
                )
            self.features = nn.Sequential(*blocks)
            self.head = nn.Sequential(
                nn.Linear(48, 16), nn.SiLU(), nn.Dropout(0.1), nn.Linear(16, 1)
            )

        def forward(self, field):
            import torch
            import torch.nn.functional as functional

            encoded = self.features(field)
            pooled = torch.cat(
                (
                    functional.adaptive_avg_pool3d(encoded, 1).flatten(1),
                    functional.adaptive_max_pool3d(encoded, 1).flatten(1),
                ),
                dim=1,
            )
            return self.head(pooled).squeeze(1)

    model = PairFieldRanker()
    if model_parameter_count(model) != 20145:
        raise AssertionError("Frozen pair-field architecture parameter count changed")
    return model


def pair_mask_from_sparse(entries: Sequence[dict]) -> np.ndarray:
    result = np.zeros((33, 33, 33), dtype=np.float32)
    for entry in entries:
        index = tuple(int(value) for value in entry["index_zyx"])
        result[index] += float(entry["weight"])
    if not np.isclose(result.sum(), 2.0, atol=1e-5):
        raise ValueError("Daughter pair mask does not have mass two")
    return result


def assemble_action_field(
    data: LockedPairFieldData,
    action: dict,
    *,
    image_mode: str = "main",
    image_parent_index: int | None = None,
) -> np.ndarray:
    target = data.parent_tensors[data.parent_index[action["parent_cache_key"]]]
    image_parent = target if image_parent_index is None else data.parent_tensors[image_parent_index]
    result = np.empty((5, 33, 33, 33), dtype=np.float32)
    if image_mode == "mask_only":
        result[0:2] = 0.0
    elif image_mode == "static_image":
        result[0] = image_parent[0]
        result[1] = image_parent[0]
    elif image_mode == "main":
        result[0:2] = image_parent[0:2]
    else:
        raise ValueError(f"Unknown image mode: {image_mode}")
    result[2] = target[2]
    result[3] = pair_mask_from_sparse(action["daughter_pair_sparse_splat"])
    result[4] = target[3]
    return result


def xy_d4(field: np.ndarray, transform: int) -> np.ndarray:
    if transform not in range(8):
        raise ValueError("XY D4 transform must be in [0, 7]")
    result = np.rot90(field, k=transform % 4, axes=(-2, -1))
    if transform >= 4:
        result = np.flip(result, axis=-1)
    return np.ascontiguousarray(result)


def geometry_features(action: dict) -> np.ndarray:
    first = np.asarray(action["child_1_relative_um"], dtype=np.float64)
    second = np.asarray(action["child_2_relative_um"], dtype=np.float64)
    first_norm = float(np.linalg.norm(first))
    second_norm = float(np.linalg.norm(second))
    denominator = max(first_norm * second_norm, 1e-12)
    cosine = float(np.clip(np.dot(first, second) / denominator, -1.0, 1.0))
    return np.asarray(
        (
            first_norm + second_norm,
            float(np.linalg.norm(first - second)),
            float(np.linalg.norm((first + second) / 2.0)),
            math.degrees(math.acos(cosine)),
        ),
        dtype=np.float64,
    )


def selected_preference_pairs(
    actions: Sequence[dict], allowed_folds: Iterable[int]
) -> tuple[np.ndarray, np.ndarray]:
    allowed = {int(value) for value in allowed_folds}
    by_event: dict[str, list[int]] = {}
    for index, row in enumerate(actions):
        if int(row["fold"]) in allowed and row["selected_for_training"]:
            by_event.setdefault(row["event_id"], []).append(index)

    by_sample: dict[str, list[str]] = {}
    valid = {}
    for event_id, indices in by_event.items():
        positives = [i for i in indices if actions[i]["official_label"] == "official_tp"]
        negatives = [i for i in indices if actions[i]["official_label"] == "official_fp"]
        if positives and negatives:
            sample_id = actions[indices[0]]["sample_id"]
            valid[event_id] = (positives, negatives)
            by_sample.setdefault(sample_id, []).append(event_id)
    if not valid:
        raise ValueError("No supervised preference pairs in selected folds")

    pairs = []
    weights = []
    sample_mass = 1.0 / len(by_sample)
    for sample_id, event_ids in sorted(by_sample.items()):
        event_mass = sample_mass / len(event_ids)
        for event_id in sorted(event_ids):
            positives, negatives = valid[event_id]
            pair_mass = event_mass / (len(positives) * len(negatives))
            for positive in positives:
                for negative in negatives:
                    pairs.append((positive, negative))
                    weights.append(pair_mass)
    pair_array = np.asarray(pairs, dtype=np.int64)
    weight_array = np.asarray(weights, dtype=np.float64)
    weight_array /= weight_array.sum()
    return pair_array, weight_array


def event_ranking_rows(actions: Sequence[dict], scores: Sequence[float]) -> list[dict]:
    by_event: dict[str, list[int]] = {}
    values = np.asarray(scores, dtype=np.float64)
    for index, row in enumerate(actions):
        by_event.setdefault(row["event_id"], []).append(index)
    rows = []
    for event_id, indices in sorted(by_event.items()):
        positives = [i for i in indices if actions[i]["official_label"] == "official_tp"]
        negatives = [i for i in indices if actions[i]["official_label"] == "official_fp"]
        if not positives:
            continue
        ranks = [
            1 + sum(
                values[other] >= values[positive] - TIE_TOLERANCE
                for other in indices
                if other != positive
            )
            for positive in positives
        ]
        best_rank = min(ranks)
        comparisons = [values[p] > values[n] + TIE_TOLERANCE for p in positives for n in negatives]
        first = actions[indices[0]]
        rows.append(
            {
                "event_id": event_id,
                "sample_id": first["sample_id"],
                "family": first["family"],
                "fold": int(first["fold"]),
                "actions": len(indices),
                "tp_variants": len(positives),
                "best_tp_rank": int(best_rank),
                "recall_at_1": float(best_rank <= 1),
                "recall_at_5": float(best_rank <= 5),
                "recall_at_10": float(best_rank <= 10),
                "mrr": 1.0 / best_rank,
                "pairwise_accuracy": float(np.mean(comparisons)),
            }
        )
    return rows


def aggregate_event_metrics(rows: Sequence[dict]) -> dict:
    if not rows:
        raise ValueError("At least one event is required")
    keys = ("recall_at_1", "recall_at_5", "recall_at_10", "mrr", "pairwise_accuracy")
    return {
        "events": len(rows),
        **{key: float(np.mean([row[key] for row in rows])) for key in keys},
    }


def stratified_metrics(rows: Sequence[dict]) -> dict:
    return {
        "pooled": aggregate_event_metrics(rows),
        "by_fold": {
            str(fold): aggregate_event_metrics([row for row in rows if row["fold"] == fold])
            for fold in sorted({row["fold"] for row in rows})
        },
        "by_family": {
            family: aggregate_event_metrics([row for row in rows if row["family"] == family])
            for family in sorted({row["family"] for row in rows})
        },
    }
