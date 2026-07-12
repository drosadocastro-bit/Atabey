import dataclasses
import numpy as np

from atabey.detection.baseline import (
    DEFAULT_VOXEL_SCALE_UM,
    VoxelScale,
    Detection,
    robust_normalize,
    threshold_local_maxima_cfar,
    _sidelobe_suppress_detections,
)
from atabey.hybrid_config import CFARThresholdMode, SideLobeSuppressionMode

def refine_detections_watershed(
    detections: list[Detection], 
    volume: np.ndarray, 
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM
) -> list[Detection]:
    """
    Refines CFAR detection coordinates using global marker-based watershed segmentation.
    
    CFAR is excellent at detecting peaks (sensitivity), but the raw intensity peak
    is structurally biased in Z due to PSF artifacts. This function:
    1. Thresholds the volume globally (normalized >= 0.65) to find all biological blobs.
    2. Uses the CFAR peaks as markers to watershed-segment the global mask, resolving dense clusters.
    3. Snaps each CFAR peak's coordinate to the unweighted geometric centroid of its watershed region.
    4. Leaves any CFAR peak that falls outside the global mask exactly as-is (preserving dim cell detections).
    """
    if not detections:
        return []

    try:
        from scipy import ndimage
        from skimage.segmentation import watershed
    except ImportError as exc:
        raise RuntimeError("scipy and skimage are required for watershed refinement") from exc

    norm_vol = robust_normalize(volume)
    global_mask = norm_vol >= 0.65
    
    Z_MAX, Y_MAX, X_MAX = global_mask.shape

    # 1. Place CFAR markers
    markers = np.zeros(global_mask.shape, dtype=np.int32)
    for i, d in enumerate(detections, start=1):
        z, y, x = int(round(d.z)), int(round(d.y)), int(round(d.x))
        z = max(0, min(z, Z_MAX - 1))
        y = max(0, min(y, Y_MAX - 1))
        x = max(0, min(x, X_MAX - 1))
        markers[z, y, x] = i

    # 2. Watershed
    # Basin is inverted raw intensity to find topological boundaries between peaks inside the mask
    labeled_cells = watershed(image=-norm_vol, markers=markers, mask=global_mask)
    
    unique_labels = np.unique(labeled_cells)
    unique_labels = unique_labels[unique_labels > 0]
    
    centroids_by_label = {}
    if len(unique_labels) > 0:
        # returns a list of tuples in the same order as unique_labels
        centroids = ndimage.center_of_mass(global_mask, labeled_cells, unique_labels)
        for label_id, centroid in zip(unique_labels, centroids):
            centroids_by_label[label_id] = centroid
            
    # 3. Refine detections
    refined = []
    for i, d in enumerate(detections, start=1):
        z, y, x = int(round(d.z)), int(round(d.y)), int(round(d.x))
        z = max(0, min(z, Z_MAX - 1))
        y = max(0, min(y, Y_MAX - 1))
        x = max(0, min(x, X_MAX - 1))
        
        label_id = labeled_cells[z, y, x]
        if label_id > 0 and label_id in centroids_by_label:
            # Snap to global watershed centroid
            cz, cy, cx = centroids_by_label[label_id]
            cz_um, cy_um, cx_um = voxel_scale.voxel_to_um(float(cz), float(cy), float(cx))
            refined.append(
                dataclasses.replace(
                    d,
                    z=float(cz),
                    y=float(cy),
                    x=float(cx),
                    z_um=float(cz_um),
                    y_um=float(cy_um),
                    x_um=float(cx_um)
                )
            )
        else:
            # Explicit fallback: if outside global mask, keep as-is
            refined.append(d)
            
    return refined


def threshold_local_maxima_cfar_watershed(
    sample_id: str,
    t: int,
    volume: np.ndarray,
    threshold: float = 0.50,
    min_distance_voxels: tuple[int, int, int] = (1, 3, 3),
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
    max_detections: int | None = None,
    cfar_training_radius_voxels: tuple[int, int, int] = (1, 7, 7),
    cfar_guard_radius_voxels: tuple[int, int, int] = (0, 1, 1),
    cfar_threshold_mode: CFARThresholdMode = "sigma",
    cfar_k_sigma: float = 1.0,
    cfar_pfa: float = 1e-4,
) -> list[Detection]:
    """CFAR detections with Watershed-based sub-voxel centroid refinement."""
    
    detections = threshold_local_maxima_cfar(
        sample_id=sample_id,
        t=t,
        volume=volume,
        threshold=threshold,
        min_distance_voxels=min_distance_voxels,
        voxel_scale=voxel_scale,
        max_detections=max_detections,
        cfar_training_radius_voxels=cfar_training_radius_voxels,
        cfar_guard_radius_voxels=cfar_guard_radius_voxels,
        cfar_threshold_mode=cfar_threshold_mode,
        cfar_k_sigma=cfar_k_sigma,
        cfar_pfa=cfar_pfa,
    )
    
    if not detections:
        return []
        
    refined = refine_detections_watershed(detections, volume, voxel_scale)
    refined.sort(key=lambda detection: (detection.t, detection.z, detection.y, detection.x))
    return refined


def threshold_local_maxima_cfar_sidelobe_watershed(
    sample_id: str,
    t: int,
    volume: np.ndarray,
    threshold: float = 0.50,
    min_distance_voxels: tuple[int, int, int] = (1, 3, 3),
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
    max_detections: int | None = None,
    cfar_training_radius_voxels: tuple[int, int, int] = (1, 7, 7),
    cfar_guard_radius_voxels: tuple[int, int, int] = (0, 1, 1),
    cfar_threshold_mode: CFARThresholdMode = "sigma",
    cfar_k_sigma: float = 1.0,
    cfar_pfa: float = 1e-4,
    sidelobe_mode: SideLobeSuppressionMode = "isotropic",
    sidelobe_radius_voxels: tuple[int, int, int] = (0, 2, 2),
    sidelobe_axial_z_radius_voxels: int = 2,
    sidelobe_axial_xy_tolerance_voxels: tuple[int, int] = (1, 1),
    sidelobe_floor_ratio: float = 0.85,
) -> list[Detection]:
    """CFAR detections with Watershed centroid refinement, followed by sidelobe suppression."""
    
    detections = threshold_local_maxima_cfar_watershed(
        sample_id=sample_id,
        t=t,
        volume=volume,
        threshold=threshold,
        min_distance_voxels=min_distance_voxels,
        voxel_scale=voxel_scale,
        max_detections=max_detections,
        cfar_training_radius_voxels=cfar_training_radius_voxels,
        cfar_guard_radius_voxels=cfar_guard_radius_voxels,
        cfar_threshold_mode=cfar_threshold_mode,
        cfar_k_sigma=cfar_k_sigma,
        cfar_pfa=cfar_pfa,
    )
    
    if not detections:
        return []

    kept = _sidelobe_suppress_detections(
        detections,
        sidelobe_mode=sidelobe_mode,
        sidelobe_radius_voxels=sidelobe_radius_voxels,
        sidelobe_axial_z_radius_voxels=sidelobe_axial_z_radius_voxels,
        sidelobe_axial_xy_tolerance_voxels=sidelobe_axial_xy_tolerance_voxels,
        sidelobe_floor_ratio=sidelobe_floor_ratio,
    )

    kept.sort(key=lambda detection: (detection.t, detection.z, detection.y, detection.x))
    return kept
