import hashlib
import importlib.util
import importlib.metadata
import json
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from test_vnstock_crawl_io import bars, io_module


@pytest.fixture
def pack_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Network forbidden'))
    io = io_module()
    monkeypatch.setattr(io, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(importlib.metadata, 'version', lambda _: '6.0.1')
    state = {'adjusted': False, 'calls': 0, 'missing_source': False, 'ticker': None}

    class Market:
        def __init__(self, source=None):
            assert source == 'fhsc'

        def equity(self, symbol):
            assert symbol in {'FPT', 'VCB'}
            return self

        def ohlcv(self, *, start, end, interval, compat, count_back):
            assert (start, end, interval, compat, count_back) == ('2026-01-01', '2026-01-02', '1D', 'v5', 5000)
            state['calls'] += 1
            frame = bars()
            frame.attrs.update(source='fhsc', profile='v5')
            if state['adjusted']:
                frame.attrs['column_basis'] = {key: 'adjusted' for key in ['open', 'high', 'low', 'close']}
            if state['missing_source']:
                frame.attrs.pop('source')
            if state['ticker'] is not None:
                frame['ticker'] = state['ticker']
            return frame

    monkeypatch.setitem(sys.modules, 'vnstock', SimpleNamespace(Market=Market))
    script = Path(io.__file__).resolve().parents[1] / 'scripts/fetch_serving_prices.py'
    spec = importlib.util.spec_from_file_location('fetch_serving_prices', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, tmp_path / 'vnstock-migration/gen6/pack', state


def run_pack(module, output):
    module.main(['--symbols', 'FPT', 'VCB', '--start', '2026-01-01', '--end', '2026-01-02',
                 '--output', str(output)])


def test_pack_does_not_claim_adjusted_prices_without_evidence(pack_setup):
    module, output, state = pack_setup
    run_pack(module, output)
    manifest = json.loads((output / 'manifest.json').read_text())
    assert manifest['price_basis'] == 'unverified'
    assert manifest['requested_provider'] == 'fhsc'
    assert manifest['source_unit'] == 'thousand_VND/share'
    assert manifest['csv_origin'] == 'vnstock_normalized'
    assert state['calls'] == 2
    for row in manifest['files']:
        assert row['sha256'] == hashlib.sha256((output / row['file']).read_bytes()).hexdigest()
        assert (row['first_date'], row['last_date']) == ('2026-01-01', '2026-01-02')
        assert row['actual_provider'] == 'fhsc'


def test_adjusted_basis_requires_provider_column_attestation(pack_setup):
    module, output, state = pack_setup
    state['adjusted'] = True
    run_pack(module, output)
    manifest = json.loads((output / 'manifest.json').read_text())
    assert manifest['price_basis'] == 'provider_adjusted'
    assert manifest['files'][0]['column_basis']['close'] == 'adjusted'


def test_pack_rejects_old_version_before_network_or_writes(pack_setup, monkeypatch):
    module, output, state = pack_setup
    monkeypatch.setattr(module.importlib.metadata, 'version', lambda _: '4.0.4')
    with pytest.raises(ValueError):
        run_pack(module, output)
    assert state['calls'] == 0
    assert not output.exists()


def test_stripped_source_cannot_attest_adjusted_pack(pack_setup):
    module, output, state = pack_setup
    state.update(adjusted=True, missing_source=True)
    with pytest.raises(ValueError):
        run_pack(module, output)
    assert not (output / 'manifest.json').exists()


def test_conflicting_provider_symbol_is_not_relabelled(pack_setup):
    module, output, state = pack_setup
    state['ticker'] = 'OTHER'
    with pytest.raises(ValueError):
        run_pack(module, output)
    assert not (output / 'FPT.csv').exists()


def test_pack_rejects_research_output_before_network(pack_setup):
    module, output, state = pack_setup
    with pytest.raises(ValueError):
        run_pack(module, output.parents[2] / 'datasets')
    assert state['calls'] == 0


@pytest.mark.parametrize('adjusted', [False, True])
def test_real_consumer_keeps_unit_basis_and_hash_gates(pack_setup, tmp_path, adjusted):
    module, output, state = pack_setup
    state['adjusted'] = adjusted
    run_pack(module, output)
    project = Path(__file__).resolve().parents[2]
    if not (project / '.venv-software/bin/python').is_file():
        pytest.skip('Consumer integration needs the optional .venv-software environment')
    generated = tmp_path / 'consumer'
    (generated / 'datasets').mkdir(parents=True)
    (generated / 'datasets/catalog.json').write_text('{}')
    script = '''
import json, socket, sys
from pathlib import Path
root, pack, generated = map(Path, sys.argv[1:])
sys.path.insert(0, str(root / 'scripts'))
for tree in ['packages', 'services']:
    sys.path.extend(str(p) for p in (root / tree).glob('*/src'))
def denied(*args, **kwargs):
    raise AssertionError('Network forbidden')
socket.socket.connect = denied
import smoke_market_quant as consumer
consumer.GENERATED = generated
try:
    _, imported = consumer.register_pack(pack)
except consumer.SmokeFailure:
    print('REJECTED')
else:
    print(json.dumps([entry for _, entry in imported]))
'''
    result = subprocess.run([str(project / '.venv-software/bin/python'), '-c', script,
                             str(project), str(output), str(generated)],
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    if adjusted:
        entries = json.loads(result.stdout)
        assert entries[0]['provider'] == 'vnstock-6.0.1-fhsc'
        assert entries[0]['source_unit'] == 'thousand_VND/share'
    else:
        assert result.stdout.strip() == 'REJECTED'
        assert json.loads((generated / 'datasets/catalog.json').read_text()) == {}
