"""Inspect the real research deliverable without approving/executing GPU work."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_research_notebook_contains_exact_sources_and_retains_frozen_v28():
    notebook = json.loads((ROOT / 'notebooks/V29A_tta_research_offline_kaggle.ipynb').read_text())
    source = ''.join(notebook['cells'][1]['source'])
    parsed = ast.parse(source)
    payload = next(n for n in ast.walk(parsed) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'b64decode')
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(ast.literal_eval(payload.args[0])))) as bundle:
        manifest = json.loads(bundle.read('package_manifest.json'))
        for name, expected in manifest['files'].items():
            data = bundle.read(name)
            assert hashlib.sha256(data).hexdigest() == expected
            if name.startswith(('src/', 'scripts/')):
                assert data == (ROOT / name).read_bytes().replace(b'\r\n', b'\n'), name
        assert manifest['candidate']['predict_config']['det_tta'] is False
        assert manifest['parent_package_manifest_sha256'] == 'fb7fde61dd8a1499cc68530cd0a0e3bc8293a803acfaf86edd2f4c67b5e097c3'
        contract = json.loads(bundle.read('v29a_contract.json'))
        assert bundle.read('v29a_contract.json') == (ROOT / 'tests/fixtures/v29a_tta.json').read_bytes()
        assert len(contract['samples']) == 199 and len(contract['timing_ids']) == 7
        assert len(contract['repeat_ids']) == 2 and len(contract['catastrophic_ids']) == 4
        assert all(len(v) == contract['quality_gates']['stratum_counts'][k] for k, v in contract['strata'].items())
        assert contract['submission_authorized'] is False
    # Stops before extraction, install, input access, GPU inference or scoring.
    with pytest.raises(AssertionError, match='approval'):
        exec(compile(source, 'V29A_unapproved', 'exec'), {})
    assert '--no-index' in source and '--no-deps' in source
    assert 'timeout = 21600 -' in source
    assert "'V29A_RESEARCH'" in source
    assert 'competition_submit' not in source
    assert 'evaluate_v29a_tta.py' not in source  # CPU scoring is a separate process.
    assert not notebook['cells'][1]['outputs'] and notebook['cells'][1]['execution_count'] is None
