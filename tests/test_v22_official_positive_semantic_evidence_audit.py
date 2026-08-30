import json
from pathlib import Path

from atabey.provenance import canonical_text_sha256

ROOT=Path(__file__).resolve().parents[1]
def _c(): return json.loads((ROOT/'tests/fixtures/v22_official_positive_semantic_evidence_audit.json').read_text(encoding='utf-8-sig'))

def test_semantic_evidence_audit_pins_sources():
    c=_c()
    for p,h in [('source_peak_csv','source_peak_sha256'),('source_action_summary','source_action_summary_sha256'),('source_development_contract','source_development_contract_sha256'),('source_proxy_audit','source_proxy_audit_sha256')]:
        assert canonical_text_sha256(ROOT/c[p])==c[h]

def test_semantic_evidence_audit_excludes_motion_and_unknown_negatives():
    c=_c(); assert c['population']['unknown_actions_remain_unknown'] is True
    assert c['labels']['sparse_absence_is_negative'] is False
    assert set(c['prohibited_features'])=={'distance','angle','velocity','prediction_error','ownership_margin','rank','ground_truth_distance'}

def test_semantic_evidence_audit_freezes_patch_and_go_gates():
    c=_c(); assert c['patch']['core_radius_um']==2.5; assert c['patch']['shell_outer_radius_um']==5.0
    d=c['decision']; assert d['raw_feature_group_auc_min']==0.65; assert d['raw_feature_groups_passing_min']==2
    assert d['best_raw_auc_advantage_over_best_confidence_min']==0.02
    assert c['evaluation']['sign_selection']=='training_folds_only'

def test_semantic_evidence_audit_keeps_scope_closed():
    c=_c(); assert c['tta_variance_available'] is False
    assert c['evaluation']['local_maxima_decision_eligible'] is False
    assert c['model_fitting_enabled'] is False and c['assignment_enabled'] is False
    assert c['graph_mutation_enabled'] is False and c['full_199_authorized'] is False
