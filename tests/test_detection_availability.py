from atabey.evaluation.detection_availability import (
    DetectionPeak,
    audit_division_detection_availability,
)


def _peak(t: int, z: float, y: float, x: float) -> DetectionPeak:
    return DetectionPeak(t=t, z_um=z, y_um=y, x_um=x)


def test_complete_triplet_requires_two_distinct_daughter_peaks():
    result = audit_division_detection_availability(
        [
            _peak(4, 0.0, 0.0, 0.0),
            _peak(5, 0.0, -1.0, 0.0),
            _peak(5, 0.0, 1.0, 0.0),
        ],
        parent_t=4,
        parent_position_um=(0.0, 0.0, 0.0),
        daughter_positions_um=((0.0, -1.0, 0.0), (0.0, 1.0, 0.0)),
    )

    assert result.complete_triplet
    assert result.distinct_daughter_pair
    assert result.parent_candidate_count == 1
    assert result.daughter_1_candidate_count == 2
    assert result.daughter_2_candidate_count == 2


def test_one_shared_peak_cannot_fill_both_daughter_roles():
    result = audit_division_detection_availability(
        [_peak(4, 0.0, 0.0, 0.0), _peak(5, 0.0, 0.0, 0.0)],
        parent_t=4,
        parent_position_um=(0.0, 0.0, 0.0),
        daughter_positions_um=((0.0, -0.5, 0.0), (0.0, 0.5, 0.0)),
    )

    assert result.parent_candidate_count == 1
    assert result.daughter_1_candidate_count == 1
    assert result.daughter_2_candidate_count == 1
    assert not result.distinct_daughter_pair
    assert not result.complete_triplet


def test_role_matching_respects_time_and_radius():
    result = audit_division_detection_availability(
        [
            _peak(3, 0.0, 0.0, 0.0),
            _peak(4, 0.0, 8.0, 0.0),
            _peak(5, 0.0, -1.0, 0.0),
            _peak(5, 0.0, 1.0, 0.0),
        ],
        parent_t=4,
        parent_position_um=(0.0, 0.0, 0.0),
        daughter_positions_um=((0.0, -1.0, 0.0), (0.0, 1.0, 0.0)),
        match_radius_um=7.0,
    )

    assert result.parent_candidate_count == 0
    assert not result.complete_triplet
