from __future__ import annotations

from dataclasses import dataclass
from math import dist
from typing import Iterable, Sequence


@dataclass(frozen=True)
class DetectionPeak:
    t: int
    z_um: float
    y_um: float
    x_um: float
    confidence: float | None = None

    @property
    def position_um(self) -> tuple[float, float, float]:
        return self.z_um, self.y_um, self.x_um


@dataclass(frozen=True)
class DivisionDetectionAvailability:
    parent_candidate_count: int
    daughter_1_candidate_count: int
    daughter_2_candidate_count: int
    parent_distance_um: float | None
    daughter_1_distance_um: float | None
    daughter_2_distance_um: float | None
    distinct_daughter_pair: bool
    complete_triplet: bool


def audit_division_detection_availability(
    peaks: Iterable[DetectionPeak],
    *,
    parent_t: int,
    parent_position_um: Sequence[float],
    daughter_positions_um: tuple[Sequence[float], Sequence[float]],
    match_radius_um: float = 7.0,
) -> DivisionDetectionAvailability:
    """Measure detector-only role availability for one GT division.

    This function does not infer edges. A complete triplet requires one parent
    peak at ``t`` and two distinct daughter peaks at ``t + 1``.
    """

    peak_list = list(peaks)
    parent_peaks = [peak for peak in peak_list if peak.t == parent_t]
    daughter_peaks = [peak for peak in peak_list if peak.t == parent_t + 1]

    parent_matches = _matches(parent_peaks, parent_position_um, match_radius_um)
    daughter_1_matches = _matches(
        daughter_peaks, daughter_positions_um[0], match_radius_um
    )
    daughter_2_matches = _matches(
        daughter_peaks, daughter_positions_um[1], match_radius_um
    )
    daughter_pair = _best_distinct_pair(daughter_1_matches, daughter_2_matches)

    return DivisionDetectionAvailability(
        parent_candidate_count=len(parent_matches),
        daughter_1_candidate_count=len(daughter_1_matches),
        daughter_2_candidate_count=len(daughter_2_matches),
        parent_distance_um=parent_matches[0][0] if parent_matches else None,
        daughter_1_distance_um=daughter_pair[0] if daughter_pair else None,
        daughter_2_distance_um=daughter_pair[1] if daughter_pair else None,
        distinct_daughter_pair=daughter_pair is not None,
        complete_triplet=bool(parent_matches and daughter_pair),
    )


def _matches(
    peaks: list[DetectionPeak],
    position_um: Sequence[float],
    radius_um: float,
) -> list[tuple[float, int]]:
    matches = [
        (dist(peak.position_um, position_um), index)
        for index, peak in enumerate(peaks)
    ]
    return sorted(
        (distance_um, index)
        for distance_um, index in matches
        if distance_um <= radius_um
    )


def _best_distinct_pair(
    daughter_1_matches: list[tuple[float, int]],
    daughter_2_matches: list[tuple[float, int]],
) -> tuple[float, float] | None:
    alternatives = [
        (distance_1 + distance_2, distance_1, distance_2, index_1, index_2)
        for distance_1, index_1 in daughter_1_matches
        for distance_2, index_2 in daughter_2_matches
        if index_1 != index_2
    ]
    if not alternatives:
        return None
    _, distance_1, distance_2, _, _ = min(alternatives)
    return distance_1, distance_2
