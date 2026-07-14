with open('kaggle_kernel/run.py', 'r') as f:
    code = f.read()

import re

# Remove the arguments from the call to _sidelobe_suppress_detections
code = re.sub(
    r'_sidelobe_suppress_detections\(\s*detections,\s*sidelobe_mode=sidelobe_mode,\s*sidelobe_radius_voxels=sidelobe_radius_voxels,\s*sidelobe_axial_z_radius_voxels=sidelobe_axial_z_radius_voxels,\s*sidelobe_axial_xy_tolerance_voxels=sidelobe_axial_xy_tolerance_voxels,\s*sidelobe_floor_ratio=sidelobe_floor_ratio,\s*\)',
    r'_sidelobe_suppress_detections(\n        detections,\n        sidelobe_radius_voxels=sidelobe_radius_voxels,\n        sidelobe_floor_ratio=sidelobe_floor_ratio,\n    )',
    code, flags=re.MULTILINE
)

# Also remove the arguments from the signature of threshold_local_maxima_cfar_sidelobe_watershed
code = re.sub(
    r'cfar_k_sigma: float = 1\.0,\s*sidelobe_mode: str = "isotropic",\s*sidelobe_radius_voxels: tuple\[int, int, int\] = \(0, 2, 2\),\s*sidelobe_axial_z_radius_voxels: int = 2,\s*sidelobe_axial_xy_tolerance_voxels: tuple\[int, int\] = \(1, 1\),\s*sidelobe_floor_ratio: float = 0\.85,',
    r'cfar_k_sigma: float = 1.0,\n    sidelobe_radius_voxels: tuple[int, int, int] = (0, 2, 2),\n    sidelobe_floor_ratio: float = 0.85,',
    code, flags=re.MULTILINE
)

with open('kaggle_kernel/run.py', 'w') as f:
    f.write(code)

print('Updated sidelobe args')
