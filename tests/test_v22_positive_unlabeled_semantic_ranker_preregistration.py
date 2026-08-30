import json
from pathlib import Path

import pytest

from atabey.provenance import canonical_text_sha256, sha256_file

ROOT=Path(__file__).resolve().parents[1]
def _c(): return json.loads((ROOT/'tests/fixtures/v22_positive_unlabeled_semantic_ranker.json').read_text(encoding='utf-8-sig'))
def test_pu_ranker_pins_sources():
 c=_c()
 for p,h in [('source_evidence_summary','source_evidence_summary_sha256'),('source_evidence_contract','source_evidence_contract_sha256'),('source_development_contract','source_development_contract_sha256')]: assert canonical_text_sha256(ROOT/c[p])==c[h]
 feature_path=ROOT/c['source_action_features']
 if not feature_path.exists(): pytest.skip('External semantic action feature archive is not mounted')
 assert sha256_file(feature_path)==c['source_action_features_sha256']
def test_pu_ranker_preserves_unknown_label_boundary():
 c=_c(); assert c['labels']['unknown_used_as_negative'] is False; assert c['labels']['unknown_in_heldout_ranking'] is True; assert c['labels']['sparse_absence_is_negative'] is False
def test_pu_ranker_freezes_audited_raw_features_and_prohibits_geometry():
 c=_c(); assert c['primary_features']==['minimum_daughter_contrast','mean_daughter_contrast','contrast_conservation_error','daughter_mass_balance','mean_daughter_anisotropy']; assert {'distance','angle','velocity','prediction_error','ownership_margin','rank'}.issubset(c['prohibited_model_inputs'])
def test_pu_ranker_is_sample_blocked_and_local_maxima_cannot_carry_go():
 c=_c(); assert c['validation']['sample_blocked'] is True; assert c['validation']['outer_folds']==[1,2,3]; assert c['validation']['local_maxima']['decision_eligible'] is False; assert c['validation']['rank_tie_policy'].startswith('pessimistic')
def test_pu_ranker_freezes_route_and_incremental_gates():
 d=_c()['decision']; assert d['action_recall_at_50_min']==.80; assert d['positive_event_recall_at_50_min']==.85; assert d['cfar_event_recall_at_50_min']==.70; assert d['components_event_recall_at_50_min']==.85; assert d['event_recall_at_50_advantage_over_best_univariate_min']==.03
def test_pu_ranker_keeps_assignment_and_graph_closed():
 c=_c(); assert c['model_fitting_enabled'] is False; assert c['assignment_enabled'] is False; assert c['graph_mutation_enabled'] is False; assert c['locked_validation_opened'] is False; assert c['full_199_authorized'] is False
