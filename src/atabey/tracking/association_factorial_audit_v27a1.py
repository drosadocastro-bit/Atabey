"""Explicit V27A.1 validity amendment; original decisions and failures preserved."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy

import numpy as np

from atabey.tracking.association_factorial_audit import (
    ARMS, CONTRASTS, RADIUS, audit_factorial_frame as parent_audit_frame,
    scientific_digest, summarize_rows as parent_summarize_rows,
)


def review_candidate_gates(frame: dict, row: dict) -> dict:
    """Independently check selected-pair geometry and the exact tie boundary."""
    h, m = row["decisions"]["H"], row["decisions"]["M0"]
    targets = np.asarray(frame["target_positions_um"], dtype=float).reshape(-1, 3)
    if not len(targets):
        if any(d["selected_index"] is not None or d["gate_eligible_target_id"] is not None
               for d in (h, m)):
            return {"classification": "INVALID_EVIDENCE", "reason": "nonempty_choice_without_targets"}
        return {"classification": "NO_TARGETS", "gate_outcome_differs": False}
    source_index = frame["source_ids"].index(row["source_id"])
    source = np.asarray(frame["source_positions_um"][source_index], dtype=float)
    errors = np.linalg.norm(targets - np.asarray(row["predicted_position_um"]), axis=1)
    steps = np.linalg.norm(targets - source, axis=1)
    exact_minima = np.flatnonzero(errors == errors.min()).tolist()
    evidence = {}
    for arm, decision in (("H", h), ("M0", m)):
        i = decision["selected_index"]
        if type(i) is not int or not 0 <= i < len(targets):
            return {"classification": "INVALID_EVIDENCE", "reason": f"{arm}_candidate_index"}
        target_id = frame["target_ids"][i]
        if decision["selected_target_id"] != target_id:
            return {"classification": "INVALID_EVIDENCE", "reason": f"{arm}_candidate_identity"}
        if not (np.isfinite(errors[i]) and np.isfinite(steps[i])
                and errors[i] == row["prediction_errors_um"][i] == decision["prediction_error_um"]
                and steps[i] == row["physical_steps_um"][i] == decision["physical_step_um"]):
            return {"classification": "INVALID_EVIDENCE", "reason": f"{arm}_distance_mismatch"}
        eligible = bool(errors[i] <= RADIUS and steps[i] <= RADIUS)
        if decision["gate_eligible_target_id"] != (target_id if eligible else None):
            return {"classification": "INVALID_EVIDENCE", "reason": f"{arm}_candidate_predicate"}
        if decision["accepted_target_id"] is not None and (
                decision["accepted_target_id"] != target_id or not eligible
                or decision["confidence"] != max(0., 1. - float(errors[i]) / RADIUS)):
            return {"classification": "INVALID_EVIDENCE", "reason": f"{arm}_confidence_or_acceptance"}
        evidence[arm] = {"selected_index": i, "target_id": target_id,
                         "prediction_error_um": float(errors[i]), "physical_step_um": float(steps[i]),
                         "candidate_eligible": eligible}
    hi, mi = h["selected_index"], m["selected_index"]
    if hi not in exact_minima or mi != exact_minima[0]:
        return {"classification": "INVALID_EVIDENCE", "reason": "motion_minimum_or_original_index"}
    different_eligibility = evidence["H"]["candidate_eligible"] != evidence["M0"]["candidate_eligible"]
    if hi == mi:
        classification = "SAME_SELECTION"
    elif errors[hi] != errors[mi]:
        return {"classification": "INVALID_EVIDENCE", "reason": "non_exact_tie"}
    else:
        classification = ("EXACT_TIE_DIFFERENT_ELIGIBILITY" if different_eligibility
                          else "EXACT_TIE_SAME_ELIGIBILITY")
    return {"classification": classification, "gate_outcome_differs": different_eligibility,
            "exact_motion_minimum_indices": exact_minima, "candidate_predicates": evidence}


def apply_amendment(parent_frame: dict) -> dict:
    """Return a new annotated result; never edit the parent record or decisions."""
    result = deepcopy(parent_frame)
    result["parent_observation_sha256"] = scientific_digest(parent_frame)
    result["parent_v27a_validity_failures"] = deepcopy(parent_frame["validity_failures"])
    reviews = {}
    new_failures = []
    for row in result["rows"]:
        review = review_candidate_gates(parent_frame, row)
        row["v27a1_gate_review"] = review
        reviews[row["source_id"]] = review
        if review["classification"] == "INVALID_EVIDENCE":
            new_failures.append({"source_id": row["source_id"], "check": "v27a1_candidate_gate_evidence",
                                 "reason": review["reason"]})
    dispositions = []
    for failure in parent_frame["validity_failures"]:
        review = reviews.get(failure.get("source_id"), {})
        admitted = (failure["check"] == "h_m0_gate_mismatch"
                    and review.get("classification") == "EXACT_TIE_DIFFERENT_ELIGIBILITY")
        dispositions.append({"parent_failure": deepcopy(failure),
                             "disposition": "RECORDED_TIE_MEDIATED_OUTCOME" if admitted else "REMAINS_INVALID"})
        if not admitted:
            new_failures.append(deepcopy(failure))
    result["amendment"] = "V27A1_CANDIDATE_WISE_GATES"
    result["parent_criterion_dispositions"] = dispositions
    result["validity_failures"] = new_failures
    return result


def audit_factorial_frame(previous, current, predecessors) -> dict:
    return apply_amendment(parent_audit_frame(previous, current, predecessors))


def summarize_rows(rows) -> dict:
    counts = Counter(parent_summarize_rows(rows))
    for row in rows:
        counts[f"v27a1_gate_review::{row['v27a1_gate_review']['classification']}"] += 1
    return dict(sorted(counts.items()))
