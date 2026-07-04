from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoxelScale:
    """Physical voxel size in microns."""

    z: float
    y: float
    x: float

    def voxel_to_um(self, z: float, y: float, x: float) -> tuple[float, float, float]:
        return z * self.z, y * self.y, x * self.x


DEFAULT_VOXEL_SCALE_UM = VoxelScale(z=1.625, y=0.40625, x=0.40625)
