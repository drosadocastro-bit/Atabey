from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CellState(str, Enum):
    STABLE = "stable"
    MOVING = "moving"
    DEFORMING = "deforming"
    PRE_DIVISION = "pre_division"
    DIVIDING = "dividing"
    POST_DIVISION = "post_division"
    OCCLUDED = "occluded"
    LOST = "lost"
    UNCERTAIN = "uncertain"
    LATENT = "latent"


@dataclass
class CellTrackMemory:
    """Track-local state used as an interpretive aid, not a truth signal."""

    track_id: str
    last_position_um: tuple[float, float, float]
    velocity_um: tuple[float, float, float] = (0.0, 0.0, 0.0)
    age: int = 0
    missing_frames: int = 0
    intensity_history: list[float] = field(default_factory=list)
    volume_history: list[int] = field(default_factory=list)
    state: CellState = CellState.UNCERTAIN
    confidence: float = 0.0
    division_potential: float = 0.0
    local_density: float = 0.0
