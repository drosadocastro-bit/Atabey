with open('kaggle_kernel/run.py', 'r') as f:
    code = f.read()

import re

# Remove cfar_threshold_mode and cfar_pfa from the threshold_local_maxima_cfar call
code = re.sub(
    r'cfar_guard_radius_voxels=cfar_guard_radius_voxels,\s*cfar_threshold_mode=cfar_threshold_mode,\s*cfar_k_sigma=cfar_k_sigma,\s*cfar_pfa=cfar_pfa,\s*\)',
    r'cfar_guard_radius_voxels=cfar_guard_radius_voxels,\n        cfar_k_sigma=cfar_k_sigma,\n    )',
    code, flags=re.MULTILINE
)

# Also remove voxel_scale from the call to threshold_local_maxima_cfar (not the watershed function itself)
code = re.sub(
    r'min_distance_voxels=min_distance_voxels,\s*voxel_scale=voxel_scale,\s*max_detections=max_detections,',
    r'min_distance_voxels=min_distance_voxels,\n        max_detections=max_detections,',
    code, flags=re.MULTILINE
)

# Remove cfar_threshold_mode and cfar_pfa from signatures of both functions
code = re.sub(
    r'cfar_guard_radius_voxels: tuple\[int, int, int\] = \(0, 1, 1\),\s*cfar_threshold_mode: str = "sigma",\s*cfar_k_sigma: float = 1.0,\s*cfar_pfa: float = 1e-4,',
    r'cfar_guard_radius_voxels: tuple[int, int, int] = (0, 1, 1),\n    cfar_k_sigma: float = 1.0,',
    code, flags=re.MULTILINE
)


with open('kaggle_kernel/run.py', 'w') as f:
    f.write(code)

print('Updated calls')
