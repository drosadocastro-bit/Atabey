"""Packaging checks inspect actual deliverables, not mocked notebook success."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('mode',['validation','submission'])
def test_notebook_bundle_is_exact_and_current(mode):
    notebook=json.loads((ROOT/f'notebooks/V28_{mode}_offline_kaggle.ipynb').read_text())
    source=''.join(notebook['cells'][1]['source'])
    tree=ast.parse(source)
    payload_call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='b64decode')
    payload=base64.b64decode(ast.literal_eval(payload_call.args[0]))
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        manifest=json.loads(z.read('package_manifest.json'))
        for name,expected in manifest['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest()==expected,name
            if name.startswith(('src/','scripts/')):
                assert z.read(name)==(ROOT/name).read_bytes().replace(b'\r\n',b'\n'),name
        assert manifest['candidate']['predict_config']['det_tta'] is False
        assert manifest['candidate']['predict_config']['det_threshold']==.97
        refs=json.loads(z.read('validation_reference.json'))
        assert len(refs['samples'])==199 and len(refs['inference_ids'])==7
        assert manifest['dataset_versions']=={'pilkwang/biohub-tracking-support-pack-50ep-v1':10,'drakus74/v22-e016-clean-checkpoint':1}
        assert len(manifest['extra_install_wheels'])==1
        assert not any('tracksdata-' in s for s in manifest['offline_install_wheels'])
    # Approval fails before package extraction, dependency installation or CUDA.
    with pytest.raises(AssertionError,match='approval'):
        exec(compile(source,'notebook','exec'),{})
    assert '--no-index' in source and '--no-deps' in source
    assert 'rglob(' not in source
    assert "'--setup-seconds'" in source
    assert 'timeout=timeout' in source


def test_no_saved_outputs_or_implicit_authority_in_notebooks():
    for mode in ['validation','submission']:
        notebook=json.loads((ROOT/f'notebooks/V28_{mode}_offline_kaggle.ipynb').read_text())
        cell=notebook['cells'][1]
        assert cell['execution_count'] is None and cell['outputs']==[]
        source=''.join(cell['source'])
        assert "'status': 'NOT_APPROVED'" in source
        assert "'authority': None" in source
        assert "if MODE == 'submission':" in source
