from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Detection:
    node_id: str
    sample_id: str
    t: int
    z: float
    y: float
    x: float
    z_um: float
    y_um: float
    x_um: float
    intensity_mean: float | None = None
    intensity_max: float | None = None
    component_volume: int | None = None
    detection_confidence: float | None = None

    @property
    def position_um(self) -> tuple[float, float, float]:
        return self.z_um, self.y_um, self.x_um


@dataclass(frozen=True)
class LineageEdge:
    source_id: str
    target_id: str
    confidence: float | None = None
    relation: str = "continuation"


@dataclass
class LineageGraph:
    sample_id: str
    detections: list[Detection] = field(default_factory=list)
    edges: list[LineageEdge] = field(default_factory=list)

    def add_detection(self, detection: Detection) -> None:
        if detection.sample_id != self.sample_id:
            raise ValueError("Detection sample_id does not match graph sample_id.")
        self.detections.append(detection)

    def add_edge(self, edge: LineageEdge) -> None:
        self.edges.append(edge)
