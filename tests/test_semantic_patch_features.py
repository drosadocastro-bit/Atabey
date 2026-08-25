import numpy as np
import pytest
from atabey.tracking.semantic_patch_features import (
    division_action_appearance_features,
    peak_patch_features,
    temporal_division_action_features,
)

def test_peak_patch_features_extract_signal_without_geometry_output():
    volume=np.full((9,31,31),10,dtype=np.float32); volume[3:6,13:18,13:18]=30
    f=peak_patch_features(volume,(4*1.625,15*.40625,15*.40625))
    assert f['patch_contrast']>0 and f['patch_signal_mass']>0 and f['patch_effective_volume']>0
    assert 0<f['patch_coverage']<=1 and set(f)=={'patch_contrast','patch_signal_mass','patch_effective_volume','patch_anisotropy','patch_coverage','shell_background','shell_robust_sigma'}

def test_action_features_encode_balance_and_conservation():
    p={'patch_contrast':10,'patch_signal_mass':100,'patch_effective_volume':50,'patch_anisotropy':2,'patch_coverage':1}
    a={'patch_contrast':5,'patch_signal_mass':50,'patch_effective_volume':25,'patch_anisotropy':2,'patch_coverage':1}
    out=division_action_appearance_features(p,a,a,parent_confidence=.9,child_1_confidence=.8,child_2_confidence=.8)
    assert out['mass_conservation_error']==pytest.approx(0); assert out['volume_conservation_error']==pytest.approx(0)
    assert out['daughter_mass_balance']==pytest.approx(1); assert out['daughter_confidence_balance']==pytest.approx(1)
    assert not any(token in name for name in out for token in ('distance','angle','velocity','prediction','rank'))



def test_temporal_action_features_capture_emergence_and_persistence():
    def patch(contrast, mass, volume, anisotropy=2.0, coverage=1.0):
        return {"patch_contrast": contrast, "patch_signal_mass": mass, "patch_effective_volume": volume, "patch_anisotropy": anisotropy, "patch_coverage": coverage}

    parent_pre = patch(10, 100, 50)
    parent_event = patch(6, 70, 40)
    child_pre = patch(1, 5, 5)
    child_event = patch(8, 45, 25)
    child_post = patch(7, 40, 23)
    out = temporal_division_action_features(parent_pre, parent_event, child_pre, child_event, child_post, child_pre, child_event, child_post)
    assert out["parent_contrast_retention"] < 0
    assert out["minimum_daughter_contrast_emergence"] > 0
    assert out["minimum_daughter_contrast_persistence"] == pytest.approx(7 / 8)
    assert out["daughter_emergence_balance"] == pytest.approx(1)
    assert out["temporal_full_coverage_fraction"] == pytest.approx(1)
    assert not any(token in name for name in out for token in ("distance", "angle", "velocity", "prediction", "ownership", "rank"))


def test_temporal_action_features_penalize_one_missing_daughter():
    def patch(contrast, mass, volume):
        return {"patch_contrast": contrast, "patch_signal_mass": mass, "patch_effective_volume": volume, "patch_anisotropy": 2.0, "patch_coverage": 1.0}

    parent = patch(10, 100, 50)
    absent = patch(0, 0, 0)
    present = patch(8, 45, 25)
    out = temporal_division_action_features(parent, parent, absent, present, present, absent, absent, absent)
    assert out["minimum_daughter_mass_emergence"] == pytest.approx(0)
    assert out["daughter_emergence_balance"] == pytest.approx(0)
    assert out["minimum_daughter_mass_persistence"] == pytest.approx(1)
