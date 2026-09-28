"""Explicit synthetic gate/serialization tests; no efficacy claims or GPU calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import zarr

from atabey.submission.v29a import candidate_config, metric_parity, quality_decision, validate_receipt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from run_v29a_tta import infer
from evaluate_v29a_tta import verify_inference


def test_only_tta_configuration_changes_and_parent_is_not_mutated():
    baseline = json.loads((ROOT / 'tests/fixtures/v28a_submission_readiness.json').read_text())['candidate']
    before = deepcopy(baseline)
    candidate = candidate_config(baseline)
    assert baseline == before
    assert candidate['predict_config']['det_tta'] is True
    candidate['predict_config']['det_tta'] = False
    assert candidate == baseline
    with pytest.raises(ValueError, match='no-TTA'):
        candidate_config({'predict_config': {'det_tta': True}})


def synthetic_decision():
    metric = {'score': .6, 'adjusted_edge_jaccard': .6, 'node_recall': .9, 'edge_fp': 10}
    rows = [{'sample_id': f'synthetic_{i}', 'baseline': deepcopy(metric),
             'tta': {**metric, 'score': .61, 'adjusted_edge_jaccard': .61}} for i in range(4)]
    summary = {arm: {**rows[0][arm], 'sample_count': 4} for arm in ('baseline', 'tta')}
    limits = {'required_samples': 4, 'minimum_score_gain': .003, 'maximum_individual_score_loss': .020,
              'maximum_node_recall_loss': .002, 'comparison_epsilon': 1e-12, 'stratum_counts': {'explicit_synthetic_group': 4}}
    return rows, summary, {'explicit_synthetic_group': deepcopy(summary)}, limits, ['synthetic_0']


def test_positive_synthetic_gates_still_never_authorize_submission():
    result = quality_decision(*synthetic_decision())
    assert result['status'] == 'GO_TO_HUMAN_SUBMISSION_REVIEW'
    assert result['submission_authorized'] is False and result['independent_validation'] is False


@pytest.mark.parametrize('gate,change', [
    ('score_gain', lambda r,s,g: s['tta'].update(score=.602)),
    ('adjusted_edge_noninferiority', lambda r,s,g: s['tta'].update(adjusted_edge_jaccard=.599)),
    ('all_strata_noninferiority', lambda r,s,g: g['explicit_synthetic_group']['tta'].update(score=.59)),
    ('improved_exceeds_regressed', lambda r,s,g: [x['tta'].update(score=.59) for x in r]),
    ('bounded_individual_loss', lambda r,s,g: r[1]['tta'].update(score=.57)),
    ('four_catastrophic_noninferiority', lambda r,s,g: r[0]['tta'].update(score=.599)),
    ('node_recall', lambda r,s,g: s['tta'].update(node_recall=.897)),
    ('official_edge_fp_nonincrease', lambda r,s,g: r[1]['tta'].update(edge_fp=11)),
])
def test_each_adverse_condition_blocks_promotion(gate, change):
    rows, summary, strata, limits, catastrophic = synthetic_decision()
    change(rows, summary, strata)
    result = quality_decision(rows, summary, strata, limits, catastrophic)
    assert result['status'] == 'NO_GO' and result['gates'][gate] is False


@pytest.mark.parametrize('change', [
    lambda r,s,g: r.pop(),
    lambda r,s,g: r.__setitem__(1, deepcopy(r[0])),
    lambda r,s,g: r[0]['tta'].update(score=None),
    lambda r,s,g: r[0]['tta'].update(node_recall=float('nan')),
    lambda r,s,g: g.clear(),
    lambda r,s,g: s['tta'].update(sample_count=3),
    lambda r,s,g: g['explicit_synthetic_group']['tta'].update(sample_count=3),
])
def test_incomplete_or_undefined_evidence_is_invalid(change):
    rows, summary, strata, limits, catastrophic = synthetic_decision()
    change(rows, summary, strata)
    with pytest.raises(ValueError):
        quality_decision(rows, summary, strata, limits, catastrophic)


def test_baseline_metric_parity_preserves_nulls_and_counts():
    expected = {'edge_tp': 7, 'division_jaccard': None, 'score': .7}
    metric_parity({**expected, 'score': .7 + 1e-13}, expected, 1e-12)
    for changed in [{'edge_tp': 8}, {'division_jaccard': 0}, {'score': .7 + 1e-9}, {'score': float('nan')}]:
        with pytest.raises(ValueError):
            metric_parity({**expected, **changed}, expected, 1e-12)


@pytest.mark.parametrize('change', [{'status':'NOT_APPROVED'}, {'scope':'V28_SUBMISSION'},
                                   {'package_manifest_sha256':'different'}, {'authority':'Codex'}, {'record':''}])
def test_prior_approval_or_missing_authority_cannot_run_v29(change):
    receipt = {'status':'APPROVED','scope':'V29A_RESEARCH','package_manifest_sha256':'test',
               'builder':'Codex','reviewer':'Danny','authority':'Danny','record':'explicit synthetic authorization fixture'}
    validate_receipt(receipt, 'test')
    with pytest.raises(ValueError):
        validate_receipt({**receipt, **change}, 'test')


def test_runtime_failure_blocks_local_scoring_before_loading_data(tmp_path):
    with pytest.raises(ValueError, match='timing-approved'):
        verify_inference(tmp_path, {'status':'NO_GO_RUNTIME'}, {}, 'test', {})


def test_saved_coordinates_reconstruct_real_adapter_graph_without_gpu(tmp_path):
    from atabey.submission.v28 import inspect_sample, build_graph, signature
    path = tmp_path / '44b6_explicit_synthetic.zarr'
    group = zarr.open_group(path, mode='w')
    group.create_array('0', data=np.zeros((2,4,4,4), dtype=np.uint16), chunks=(1,4,4,4))
    group.attrs.update({'multiscales':[{'axes':[{'name':n,'unit':'second' if n=='t' else 'micrometer'} for n in 'tzyx'],
        'datasets':[{'path':'0','coordinateTransformations':[{'type':'scale','scale':[1,1.625,.40625,.40625]}]}]}],
        'image_statistics':{'quantiles':{'0.001':0,'0.999':100}}})
    coordinates = np.array([[0,1,1,1],[1,1,1,1]], dtype=np.int16)
    def explicit_fake_predict(_):
        return coordinates, {'inference_seconds':.01}
    output = tmp_path / 'research'
    for folder in ('coordinates', 'records'):
        (output / folder).mkdir(parents=True)
    expected = {'image_metadata':inspect_sample(path),'pruning_eligible':False}
    record = infer(path, explicit_fake_predict, expected, output)
    reconstructed, _ = build_graph(path.stem, np.load(output / record['coordinates']['path'], allow_pickle=False), False)
    assert signature(reconstructed) == record['graph_signature_sha256']
    # JSON normalizes the adapter's tuple of sampled timepoints to a list.
    assert json.loads((output/'records'/(path.stem+'.json')).read_text()) == json.loads(json.dumps(record))
    with pytest.raises(ValueError, match='overwrite'):
        infer(path, explicit_fake_predict, expected, output)


def test_gpu_entrypoint_has_no_ground_truth_or_scoring_import():
    source = (ROOT / 'scripts/run_v29a_tta.py').read_text()
    assert 'read_geff_graph' not in source and 'evaluate_official_tracking' not in source
    assert 'write_test_submission' in source and 'v29a_preview.csv' in source
