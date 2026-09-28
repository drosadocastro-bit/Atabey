"""V29A research gates; an opened-cohort gain is not submission authority."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def tree_identity(path):
    path = Path(path)
    require(path.is_dir(), f'Missing directory: {path}')
    files = [{'path': p.relative_to(path).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
             for p in sorted(path.rglob('*')) if p.is_file()]
    require(files, f'Empty directory: {path}')
    return {'files': len(files), 'bytes': sum(f['bytes'] for f in files), 'sha256': digest(files)}


def candidate_config(baseline):
    require(baseline['predict_config']['det_tta'] is False, 'Expected V28 no-TTA baseline')
    candidate = deepcopy(baseline)
    candidate['predict_config']['det_tta'] = True
    return candidate


def validate_receipt(receipt, manifest_sha):
    require(receipt.get('status') == 'APPROVED', 'Exact package approval required')
    require(receipt.get('scope') == 'V29A_RESEARCH', 'Research scope required')
    require(receipt.get('package_manifest_sha256') == manifest_sha, 'Approval/package mismatch')
    require(receipt.get('reviewer') == receipt.get('authority') == 'Danny', 'Human authority required')
    require(receipt.get('builder') == 'Codex' and bool(receipt.get('record')), 'Approval record required')


def metric_parity(actual, expected, tolerance):
    require(set(actual) == set(expected), 'Metric schema drift')
    for key, value in expected.items():
        observed = actual[key]
        if value is None or isinstance(value, int):
            require(observed == value, f'Historical metric mismatch: {key}')
        else:
            require(isinstance(observed, (float, int)) and math.isfinite(observed)
                    and math.isclose(observed, value, rel_tol=0, abs_tol=tolerance),
                    f'Historical metric mismatch: {key}')


def quality_decision(rows, summaries, strata, limits, catastrophic_ids):
    """Consume official metrics only after exact coverage and runtime verification."""
    require(len(rows) == limits['required_samples'] and len({r['sample_id'] for r in rows}) == len(rows),
            'Incomplete or duplicate cohort')
    needed = ('score', 'adjusted_edge_jaccard', 'node_recall')
    for row in rows:
        for arm in ('baseline', 'tta'):
            require(all(isinstance(row[arm][k], (int, float)) and math.isfinite(row[arm][k]) for k in needed),
                    'Undefined primary or guard metric')
    require(set(catastrophic_ids) <= {r['sample_id'] for r in rows}, 'Missing catastrophic cases')
    require(set(strata) == set(limits['stratum_counts']), 'Missing required stratum')
    require(all(strata[k][arm]['sample_count'] == count for k, count in limits['stratum_counts'].items()
                for arm in ('baseline', 'tta')), 'Stratum coverage differs from contract')
    require(all(summaries[arm]['sample_count'] == len(rows) for arm in ('baseline', 'tta')), 'Summary coverage mismatch')
    for group in [summaries, *strata.values()]:
        require(all(group[a]['sample_count'] > 0 and
                    all(isinstance(group[a][k], (int, float)) and math.isfinite(group[a][k]) for k in needed)
                    for a in ('baseline', 'tta')), 'Undefined or empty summary')
    deltas = {r['sample_id']: r['tta']['score'] - r['baseline']['score'] for r in rows}
    improved = sum(d > limits['comparison_epsilon'] for d in deltas.values())
    regressed = sum(d < -limits['comparison_epsilon'] for d in deltas.values())
    gates = {
        'score_gain': summaries['tta']['score'] - summaries['baseline']['score'] >= limits['minimum_score_gain'],
        'adjusted_edge_noninferiority': summaries['tta']['adjusted_edge_jaccard'] >= summaries['baseline']['adjusted_edge_jaccard'],
        'all_strata_noninferiority': all(v['tta']['score'] >= v['baseline']['score'] for v in strata.values()),
        'improved_exceeds_regressed': improved > regressed,
        'bounded_individual_loss': min(deltas.values()) >= -limits['maximum_individual_score_loss'],
        'four_catastrophic_noninferiority': all(deltas[sid] >= 0 for sid in catastrophic_ids),
        'node_recall': summaries['tta']['node_recall'] >= summaries['baseline']['node_recall'] - limits['maximum_node_recall_loss'],
        'official_edge_fp_nonincrease': sum(r['tta']['edge_fp'] for r in rows) <= sum(r['baseline']['edge_fp'] for r in rows),
    }
    return {'status': 'GO_TO_HUMAN_SUBMISSION_REVIEW' if all(gates.values()) else 'NO_GO',
            'gates': gates, 'improved': improved, 'regressed': regressed,
            'unchanged': len(rows) - improved - regressed, 'score_deltas': deltas,
            'submission_authorized': False, 'independent_validation': False}
