from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from atabey.detection.baseline import robust_normalize


FIELD_SIZE = 33
HALF_EXTENT_UM = 16.0
SPACING_UM = 1.0
PARENT_CHANNELS = 4
ASSEMBLED_CHANNELS = 5
ACTION_METADATA_BYTES = 256


@dataclass(frozen=True)
class StorageEstimate:
    parent_fields: int
    actions: int
    cached_bytes: int
    naive_assembled_bytes: int

    @property
    def cached_gib(self) -> float:
        return self.cached_bytes / float(1024**3)

    @property
    def naive_assembled_gib(self) -> float:
        return self.naive_assembled_bytes / float(1024**3)


def _position(value) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (3,):
        raise ValueError("Expected a physical ZYX position with three values")
    return result


def field_offsets_um() -> np.ndarray:
    return np.linspace(
        -HALF_EXTENT_UM,
        HALF_EXTENT_UM,
        FIELD_SIZE,
        dtype=np.float64,
    )


def physical_query_grid(parent_position_um) -> np.ndarray:
    center = _position(parent_position_um)
    offsets = field_offsets_um()
    zz, yy, xx = np.meshgrid(offsets, offsets, offsets, indexing="ij")
    return np.stack(
        (zz + center[0], yy + center[1], xx + center[2]),
        axis=0,
    )


def _sample_image(volume: np.ndarray, query_um: np.ndarray, voxel_scale_um) -> np.ndarray:
    try:
        from scipy.ndimage import map_coordinates
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("scipy is required for pair-field extraction") from exc

    scale = _position(voxel_scale_um)
    coordinates = query_um / scale[:, None, None, None]
    normalized = robust_normalize(volume, lower=1.0, upper=99.9)
    sampled = map_coordinates(
        normalized,
        coordinates,
        order=1,
        mode="constant",
        cval=0.0,
        prefilter=False,
    )
    return sampled.astype(np.float32, copy=False)


def _coverage_mask(
    query_um: np.ndarray,
    spatial_shape,
    voxel_scale_um,
) -> np.ndarray:
    shape = np.asarray(spatial_shape, dtype=np.int64)
    if shape.shape != (3,) or np.any(shape <= 0):
        raise ValueError("spatial_shape must contain three positive dimensions")
    high = (shape.astype(np.float64) - 1.0) * _position(voxel_scale_um)
    valid = np.all(
        (query_um >= 0.0) & (query_um <= high[:, None, None, None]),
        axis=0,
    )
    return valid.astype(np.float32)


def trilinear_splat(relative_position_um) -> np.ndarray:
    relative = _position(relative_position_um)
    index = relative / SPACING_UM + HALF_EXTENT_UM / SPACING_UM
    if np.any(index < 0.0) or np.any(index > FIELD_SIZE - 1):
        raise ValueError("Position falls outside the frozen pair field")

    low = np.floor(index).astype(int)
    fraction = index - low
    high = np.minimum(low + 1, FIELD_SIZE - 1)
    result = np.zeros((FIELD_SIZE, FIELD_SIZE, FIELD_SIZE), dtype=np.float32)
    for z_choice in (0, 1):
        for y_choice in (0, 1):
            for x_choice in (0, 1):
                choices = np.asarray((z_choice, y_choice, x_choice), dtype=int)
                target = np.where(choices == 0, low, high)
                weights = np.where(choices == 0, 1.0 - fraction, fraction)
                weight = float(np.prod(weights))
                if weight:
                    result[tuple(target)] += weight
    return result


def daughter_pair_mask(child_1_relative_um, child_2_relative_um) -> np.ndarray:
    return trilinear_splat(child_1_relative_um) + trilinear_splat(
        child_2_relative_um
    )


def extract_parent_field(
    volume_t: np.ndarray,
    volume_t_plus_1: np.ndarray,
    parent_position_um,
    *,
    voxel_scale_um=(1.625, 0.40625, 0.40625),
) -> np.ndarray:
    if volume_t.shape != volume_t_plus_1.shape:
        raise ValueError("The two source frames must have the same spatial shape")
    if volume_t.ndim != 3:
        raise ValueError("Pair-field source frames must be three-dimensional")

    query = physical_query_grid(parent_position_um)
    image_t = _sample_image(volume_t, query, voxel_scale_um)
    image_t_plus_1 = _sample_image(volume_t_plus_1, query, voxel_scale_um)
    parent_mask = trilinear_splat((0.0, 0.0, 0.0))
    coverage = _coverage_mask(query, volume_t.shape, voxel_scale_um)
    field = np.stack(
        (image_t, image_t_plus_1, parent_mask, coverage),
        axis=0,
    ).astype(np.float32, copy=False)
    if field.shape != (PARENT_CHANNELS, FIELD_SIZE, FIELD_SIZE, FIELD_SIZE):
        raise AssertionError("Unexpected parent-field shape")
    return field


def assemble_pair_field(
    parent_field: np.ndarray,
    child_1_relative_um,
    child_2_relative_um,
) -> np.ndarray:
    expected = (PARENT_CHANNELS, FIELD_SIZE, FIELD_SIZE, FIELD_SIZE)
    if parent_field.shape != expected:
        raise ValueError(f"Expected parent field shape {expected}")
    pair_mask = daughter_pair_mask(child_1_relative_um, child_2_relative_um)
    assembled = np.stack(
        (
            parent_field[0],
            parent_field[1],
            parent_field[2],
            pair_mask,
            parent_field[3],
        ),
        axis=0,
    ).astype(np.float32, copy=False)
    return assembled


def tensor_sha256(tensor: np.ndarray) -> str:
    canonical = np.ascontiguousarray(tensor, dtype=np.float32)
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def estimate_storage(parent_fields: int, actions: int) -> StorageEstimate:
    if parent_fields < 0 or actions < 0:
        raise ValueError("Storage counts cannot be negative")
    voxels = FIELD_SIZE**3
    cached_bytes = (
        parent_fields * PARENT_CHANNELS * voxels * np.dtype(np.float32).itemsize
        + actions * ACTION_METADATA_BYTES
    )
    naive_bytes = (
        actions * ASSEMBLED_CHANNELS * voxels * np.dtype(np.float32).itemsize
    )
    return StorageEstimate(
        parent_fields=parent_fields,
        actions=actions,
        cached_bytes=int(cached_bytes),
        naive_assembled_bytes=int(naive_bytes),
    )


def synthetic_integrity_check() -> dict[str, bool]:
    shape = (41, 41, 41)
    z, y, x = np.indices(shape, dtype=np.float32)
    volume_t = z + 2.0 * y + 3.0 * x
    volume_t_plus_1 = 0.5 * z + y + 4.0 * x
    parent = (20.0, 20.0, 20.0)
    first = (3.25, -2.5, 4.75)
    second = (-4.0, 3.5, -1.25)

    parent_field_a = extract_parent_field(
        volume_t,
        volume_t_plus_1,
        parent,
        voxel_scale_um=(1.0, 1.0, 1.0),
    )
    parent_field_b = extract_parent_field(
        volume_t,
        volume_t_plus_1,
        parent,
        voxel_scale_um=(1.0, 1.0, 1.0),
    )
    forward = assemble_pair_field(parent_field_a, first, second)
    reversed_pair = assemble_pair_field(parent_field_a, second, first)
    return {
        "shape": forward.shape
        == (ASSEMBLED_CHANNELS, FIELD_SIZE, FIELD_SIZE, FIELD_SIZE),
        "finite": bool(np.isfinite(forward).all()),
        "image_range": bool(
            np.all((forward[:2] >= 0.0) & (forward[:2] <= 1.0))
        ),
        "coverage_binary": bool(
            set(np.unique(forward[4]).tolist()).issubset({0.0, 1.0})
        ),
        "parent_mass": bool(np.isclose(forward[2].sum(), 1.0, atol=1e-5)),
        "daughter_mass": bool(np.isclose(forward[3].sum(), 2.0, atol=1e-5)),
        "daughter_swap_invariant": bool(np.array_equal(forward, reversed_pair)),
        "deterministic_hash": tensor_sha256(parent_field_a)
        == tensor_sha256(parent_field_b),
    }
