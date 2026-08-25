import numpy as np
import pytest

from atabey.tracking.pair_field import (
    assemble_pair_field,
    daughter_pair_mask,
    estimate_storage,
    extract_parent_field,
    field_offsets_um,
    synthetic_integrity_check,
    tensor_sha256,
    trilinear_splat,
)


def test_pair_field_offsets_and_splats_follow_frozen_geometry():
    offsets = field_offsets_um()
    assert offsets.shape == (33,)
    assert offsets[0] == -16.0
    assert offsets[-1] == 16.0
    assert np.allclose(np.diff(offsets), 1.0)

    parent = trilinear_splat((0.0, 0.0, 0.0))
    daughters = daughter_pair_mask((2.25, -3.5, 4.75), (-4.0, 2.5, -1.25))
    assert parent.shape == (33, 33, 33)
    assert parent.sum() == pytest.approx(1.0, abs=1e-5)
    assert daughters.sum() == pytest.approx(2.0, abs=1e-5)


def test_pair_field_daughter_order_is_exactly_invariant():
    parent_field = np.zeros((4, 33, 33, 33), dtype=np.float32)
    first = (2.25, -3.5, 4.75)
    second = (-4.0, 2.5, -1.25)
    forward = assemble_pair_field(parent_field, first, second)
    reverse = assemble_pair_field(parent_field, second, first)

    assert np.array_equal(forward, reverse)
    assert tensor_sha256(forward) == tensor_sha256(reverse)


def test_parent_field_extraction_exposes_boundary_coverage():
    shape = (41, 41, 41)
    z, y, x = np.indices(shape, dtype=np.float32)
    volume_t = z + y + x
    volume_t1 = z + 2 * y + 3 * x

    center = extract_parent_field(
        volume_t,
        volume_t1,
        (20.0, 20.0, 20.0),
        voxel_scale_um=(1.0, 1.0, 1.0),
    )
    boundary = extract_parent_field(
        volume_t,
        volume_t1,
        (0.0, 0.0, 0.0),
        voxel_scale_um=(1.0, 1.0, 1.0),
    )

    assert center.shape == (4, 33, 33, 33)
    assert center.dtype == np.float32
    assert center[3].mean() == pytest.approx(1.0)
    assert 0.0 < boundary[3].mean() < 1.0
    assert np.all((boundary[:2] >= 0.0) & (boundary[:2] <= 1.0))


def test_storage_estimate_rewards_parent_cache_without_writing_tensors():
    estimate = estimate_storage(parent_fields=100, actions=10_000)

    assert estimate.cached_bytes > 0
    assert estimate.naive_assembled_bytes > estimate.cached_bytes
    assert estimate.cached_gib < estimate.naive_assembled_gib


def test_synthetic_pair_field_integrity_contract_passes():
    checks = synthetic_integrity_check()

    assert checks
    assert all(checks.values())
