from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CFARRoutePolicy = Literal["merged_all", "merged_6bba_only"]
CFARThresholdMode = Literal["sigma", "pfa"]
SideLobeSuppressionMode = Literal["isotropic", "axial"]


@dataclass(frozen=True)
class GuardrailSettings:
    spike_multiplier: float = 1.8
    min_history: int = 6
    history_window: int = 12
    min_absolute_count: int = 1200
    fallback_threshold: float = 0.65


@dataclass(frozen=True)
class HybridFrozenDefaults:
    cfar_threshold: float = 0.50
    cfar_training_radius_voxels: tuple[int, int, int] = (1, 6, 6)
    cfar_guard_radius_voxels: tuple[int, int, int] = (0, 1, 1)
    cfar_threshold_mode: CFARThresholdMode = "sigma"
    cfar_k_sigma: float = 1.1
    cfar_pfa: float = 1e-4
    sidelobe_mode: SideLobeSuppressionMode = "isotropic"
    sidelobe_radius_voxels: tuple[int, int, int] = (1, 12, 12)
    sidelobe_axial_z_radius_voxels: int = 2
    sidelobe_axial_xy_tolerance_voxels: tuple[int, int] = (1, 1)
    sidelobe_floor_ratio: float = 0.85
    max_detections_per_timepoint: int = 900
    cfar_route_policy: CFARRoutePolicy = "merged_6bba_only"
    cfar_link_strategy: str = "motion_mutual"
    cfar_max_link_distance_um: float = 9.0
    latent_shadow_window_frames: int = 2
    latent_shadow_max_link_distance_um: float = 9.0
    mitosis_shadow_distance_um: float = 3.0
    mitosis_shadow_intensity_tolerance: float = 0.40


DEFAULT_GUARDRAIL_SETTINGS = GuardrailSettings()
DEFAULT_HYBRID_FROZEN_DEFAULTS = HybridFrozenDefaults()
