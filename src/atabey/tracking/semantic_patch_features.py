from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np


def peak_patch_features(
    volume: np.ndarray,
    position_um: Sequence[float],
    *,
    voxel_scale_um: Sequence[float] = (1.625, 0.40625, 0.40625),
    core_radius_um: float = 2.5,
    shell_inner_radius_um: float = 3.5,
    shell_outer_radius_um: float = 5.0,
    threshold_mad: float = 3.0,
) -> dict[str, float]:
    data=np.asarray(volume)
    scale=np.asarray(voxel_scale_um,dtype=float); position=np.asarray(position_um,dtype=float)
    if data.ndim!=3 or scale.shape!=(3,) or position.shape!=(3,): raise ValueError('Expected 3D volume and three-axis coordinates')
    if np.any(scale<=0) or not (0<core_radius_um<shell_inner_radius_um<shell_outer_radius_um): raise ValueError('Invalid physical patch geometry')
    center=position/scale; radius_vox=np.ceil(shell_outer_radius_um/scale).astype(int)
    lo=np.floor(center).astype(int)-radius_vox; hi=np.floor(center).astype(int)+radius_vox+1
    full_axes=[np.arange(lo[a],hi[a]) for a in range(3)]
    full_grid=np.meshgrid(*full_axes,indexing='ij'); full_delta=[full_grid[a]*scale[a]-position[a] for a in range(3)]
    full_dist=np.sqrt(sum(delta*delta for delta in full_delta)); expected_core=int(np.sum(full_dist<=core_radius_um))
    clipped_lo=np.maximum(lo,0); clipped_hi=np.minimum(hi,np.asarray(data.shape));
    if np.any(clipped_lo>=clipped_hi): raise ValueError('Peak position lies outside volume')
    slices=tuple(slice(int(clipped_lo[a]),int(clipped_hi[a])) for a in range(3)); patch=data[slices].astype(float,copy=False)
    axes=[np.arange(clipped_lo[a],clipped_hi[a]) for a in range(3)]; grid=np.meshgrid(*axes,indexing='ij'); delta=[grid[a]*scale[a]-position[a] for a in range(3)]
    distance=np.sqrt(sum(value*value for value in delta)); core=distance<=core_radius_um; shell=(distance>=shell_inner_radius_um)&(distance<=shell_outer_radius_um)
    if not np.any(core) or not np.any(shell): raise ValueError('Patch does not contain required core and shell voxels')
    core_values=patch[core]; shell_values=patch[shell]; background=float(np.median(shell_values)); mad=float(np.median(np.abs(shell_values-background))); robust_sigma=1.4826*mad
    signal=np.maximum(core_values-background,0.0); voxel_volume=float(np.prod(scale)); mass=float(signal.sum()*voxel_volume)
    effective=float(np.sum(core_values>background+threshold_mad*robust_sigma)*voxel_volume)
    contrast=float((float(core_values.mean())-background)/(robust_sigma+1.0))
    core_coords=np.column_stack([value[core] for value in delta]);
    if signal.sum()>1e-12:
        mean=np.average(core_coords,axis=0,weights=signal); centered=core_coords-mean; covariance=(centered*signal[:,None]).T@centered/signal.sum(); eigen=np.linalg.eigvalsh(covariance); positive=eigen[eigen>1e-9]; anisotropy=float(np.sqrt(eigen.max()/positive.min())) if positive.size else 1.0
    else: anisotropy=1.0
    return {'patch_contrast':contrast,'patch_signal_mass':mass,'patch_effective_volume':effective,'patch_anisotropy':anisotropy,'patch_coverage':float(np.sum(core)/expected_core),'shell_background':background,'shell_robust_sigma':robust_sigma}


def division_action_appearance_features(parent: Mapping[str,float], child_1: Mapping[str,float], child_2: Mapping[str,float], *, parent_confidence: float, child_1_confidence: float, child_2_confidence: float) -> dict[str,float]:
    def balance(a,b):
        high=max(abs(float(a)),abs(float(b))); return min(abs(float(a)),abs(float(b)))/high if high>1e-12 else 1.0
    def conservation(p,a,b):
        p=float(p); total=float(a)+float(b); return abs(total-p)/(abs(total)+abs(p)+1e-12)
    pc=float(parent['patch_contrast']); c1=float(child_1['patch_contrast']); c2=float(child_2['patch_contrast'])
    pm=float(parent['patch_signal_mass']); m1=float(child_1['patch_signal_mass']); m2=float(child_2['patch_signal_mass'])
    pv=float(parent['patch_effective_volume']); v1=float(child_1['patch_effective_volume']); v2=float(child_2['patch_effective_volume'])
    pa=float(parent['patch_anisotropy']); a1=float(child_1['patch_anisotropy']); a2=float(child_2['patch_anisotropy'])
    return {
      'mean_detection_confidence':float(np.mean([parent_confidence,child_1_confidence,child_2_confidence])),
      'minimum_detection_confidence':float(min(parent_confidence,child_1_confidence,child_2_confidence)),
      'daughter_confidence_balance':balance(child_1_confidence,child_2_confidence),
      'parent_contrast':pc,'minimum_daughter_contrast':min(c1,c2),'mean_daughter_contrast':0.5*(c1+c2),'daughter_contrast_balance':balance(c1,c2),'contrast_conservation_error':conservation(pc,c1,c2),
      'mass_conservation_error':conservation(pm,m1,m2),'daughter_mass_balance':balance(m1,m2),
      'volume_conservation_error':conservation(pv,v1,v2),'daughter_volume_balance':balance(v1,v2),
      'mean_daughter_anisotropy':0.5*(a1+a2),'daughter_anisotropy_difference':abs(a1-a2),'parent_daughter_anisotropy_change':abs(0.5*(a1+a2)-pa),
      'minimum_patch_coverage':min(float(parent['patch_coverage']),float(child_1['patch_coverage']),float(child_2['patch_coverage']))
    }


def temporal_division_action_features(
    parent_pre: Mapping[str, float],
    parent_event: Mapping[str, float],
    child_1_pre: Mapping[str, float],
    child_1_event: Mapping[str, float],
    child_1_post: Mapping[str, float],
    child_2_pre: Mapping[str, float],
    child_2_event: Mapping[str, float],
    child_2_post: Mapping[str, float],
) -> dict[str, float]:
    def signed_change(before: float, after: float) -> float:
        before = float(before)
        after = float(after)
        return (after - before) / (abs(after) + abs(before) + 1e-12)

    def positive_retention(before: float, after: float) -> float:
        before = max(float(before), 0.0)
        after = max(float(after), 0.0)
        if before <= 1e-12:
            return 1.0 if after <= 1e-12 else 0.0
        return min(after / before, 1.0)

    def balance(first: float, second: float) -> float:
        first = abs(float(first))
        second = abs(float(second))
        high = max(first, second)
        return min(first, second) / high if high > 1e-12 else 1.0

    def conservation(parent: float, first: float, second: float) -> float:
        parent = float(parent)
        total = float(first) + float(second)
        return abs(total - parent) / (abs(total) + abs(parent) + 1e-12)

    contrast_emergence = [
        signed_change(child_1_pre["patch_contrast"], child_1_event["patch_contrast"]),
        signed_change(child_2_pre["patch_contrast"], child_2_event["patch_contrast"]),
    ]
    mass_emergence = [
        signed_change(child_1_pre["patch_signal_mass"], child_1_event["patch_signal_mass"]),
        signed_change(child_2_pre["patch_signal_mass"], child_2_event["patch_signal_mass"]),
    ]
    contrast_persistence = [
        positive_retention(child_1_event["patch_contrast"], child_1_post["patch_contrast"]),
        positive_retention(child_2_event["patch_contrast"], child_2_post["patch_contrast"]),
    ]
    mass_persistence = [
        positive_retention(child_1_event["patch_signal_mass"], child_1_post["patch_signal_mass"]),
        positive_retention(child_2_event["patch_signal_mass"], child_2_post["patch_signal_mass"]),
    ]
    coverage = [
        parent_pre["patch_coverage"], parent_event["patch_coverage"],
        child_1_pre["patch_coverage"], child_1_event["patch_coverage"], child_1_post["patch_coverage"],
        child_2_pre["patch_coverage"], child_2_event["patch_coverage"], child_2_post["patch_coverage"],
    ]
    return {
        "parent_contrast_retention": signed_change(parent_pre["patch_contrast"], parent_event["patch_contrast"]),
        "parent_mass_retention": signed_change(parent_pre["patch_signal_mass"], parent_event["patch_signal_mass"]),
        "minimum_daughter_contrast_emergence": min(contrast_emergence),
        "minimum_daughter_mass_emergence": min(mass_emergence),
        "daughter_emergence_balance": balance(*mass_emergence),
        "minimum_daughter_contrast_persistence": min(contrast_persistence),
        "minimum_daughter_mass_persistence": min(mass_persistence),
        "daughter_persistence_balance": balance(*mass_persistence),
        "temporal_mass_conservation_error": conservation(parent_pre["patch_signal_mass"], child_1_post["patch_signal_mass"], child_2_post["patch_signal_mass"]),
        "temporal_volume_conservation_error": conservation(parent_pre["patch_effective_volume"], child_1_post["patch_effective_volume"], child_2_post["patch_effective_volume"]),
        "temporal_daughter_anisotropy_agreement": balance(child_1_post["patch_anisotropy"], child_2_post["patch_anisotropy"]),
        "temporal_full_coverage_fraction": float(np.mean(np.asarray(coverage, dtype=float) >= 1.0 - 1e-12)),
    }
