import importlib
import importlib.metadata
import json
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from test_vnstock_crawl_io import bars, io_module

pd = pytest.importorskip('pandas', reason='Run ingestion tests in ~/.venv_6x')


@pytest.fixture
def stock_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Network forbidden'))
    io = io_module()
    monkeypatch.setattr(io, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(importlib.metadata, 'version', lambda _: '6.0.1')
    calls = []

    class Market:
        def __init__(self, source=None):
            assert source == 'fhsc'

        def equity(self, symbol):
            calls.append(('equity', symbol))
            return self

        def etf(self, symbol):
            calls.append(('etf', symbol))
            return self

        def index(self, symbol):
            calls.append(('index', symbol))
            return self

        def ohlcv(self, *, start, end, interval, compat):
            assert (start, end, interval, compat) == ('2026-01-01', '2026-01-02', '1D', 'v5')
            frame = bars()
            frame.attrs.update(source='fhsc', profile='v5')
            return frame

    class Reference:
        def __init__(self, source=None):
            assert source == 'fhsc'

        def index(self, symbol):
            assert symbol == 'VN30'
            return self

        def constituents(self):
            frame = pd.DataFrame({'symbol': [f'A{i}' for i in range(30)]})
            frame.attrs.update(source='fhsc', profile='v5')
            return frame

    monkeypatch.setitem(sys.modules, 'vnstock', SimpleNamespace(Market=Market, Reference=Reference))
    module = importlib.import_module('crawl.stock')
    monkeypatch.setattr(module.time, 'sleep', lambda *_: None)
    return module, tmp_path / 'vnstock-migration/gen6/stocks', calls


def test_stock_etf_and_index_export_contract_without_touching_research(stock_setup):
    stock, output, calls = stock_setup
    assert hasattr(stock, 'main'), 'Crawler has no safe CLI'
    stock.main(['--output-root', str(output), '--start', '2026-01-01', '--end', '2026-01-02',
                '--symbols', 'FPT', 'E1VFVN30', '--index', 'VNINDEX'])
    assert calls == [('equity', 'FPT'), ('etf', 'E1VFVN30'), ('index', 'VNINDEX')]
    for folder, symbol in [('stocks', 'FPT'), ('stocks', 'E1VFVN30'), ('indices', 'VNINDEX')]:
        frame = pd.read_csv(output / folder / 'full' / f'{symbol}.csv')
        assert frame.columns.tolist() == ['date', 'open', 'high', 'low', 'close', 'volume', 'symbol']
        assert frame['date'].tolist() == ['2026-01-01', '2026-01-02']
        assert frame['close'].tolist() == [25.5, 26.5]
        assert frame['symbol'].tolist() == [symbol, symbol]
    assert json.loads((output / 'manifest.json').read_text())['requested_provider'] == 'fhsc'


VNINDEX_FHSC_ROWS = [
    ('2021-02-17T00:00:00Z', 1127.46, 1151.54, 1127.46, 1155.78, 459215000),
    ('2021-12-10T00:00:00Z', 1469.83, 1475.85, 1469.68, 1463.54, 780120100),
    ('2023-05-15T00:00:00Z', 1074.82, 1076.32, 1067.15, 1065.71, 791524900),
    ('2024-05-06T00:00:00Z', 1226.89, 1226.89, 1224.22, 1241.58, 666198300),
]
VNINDEX_DNSE_OHLC = [
    [1127.46, 1155.78, 1127.46, 1155.78],
    [1470.55, 1475.85, 1461.78, 1463.54],
    [1074.82, 1076.32, 1065.71, 1065.71],
    [1226.89, 1241.58, 1224.22, 1241.58],
]


def historical_stock_args(output, monkeypatch, rows, *, symbol='VNINDEX'):
    frame = pd.DataFrame(rows, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    frame.attrs.update(source='fhsc', profile='v5')
    monkeypatch.setattr(sys.modules['vnstock'].Market, 'ohlcv', lambda *_a, **_kw: frame)
    asset_option = '--index' if symbol == 'VNINDEX' else '--symbols'
    return ['--output-root', str(output), '--start', '2020-01-01', '--end', '2026-11-21', asset_option, symbol]


def test_vnindex_reconciles_four_reviewed_bars_and_records_sources(stock_setup, monkeypatch):
    stock, output, _ = stock_setup
    clean_bar = ('2021-02-18T00:00:00Z', 1157.10, 1174.38, 1148.66, 1174.38, 585040700)
    args = historical_stock_args(output, monkeypatch, [*VNINDEX_FHSC_ROWS, clean_bar])
    stock.main(args)

    full = pd.read_csv(output / 'indices/full/VNINDEX.csv').set_index('date')
    manifest = json.loads((output / 'manifest.json').read_text())
    replacements = manifest['calls'][0]['replacements']
    assert [entry['date'] for entry in replacements] == [row[0][:10] for row in VNINDEX_FHSC_ROWS]
    for original, expected, entry in zip(VNINDEX_FHSC_ROWS, VNINDEX_DNSE_OHLC, replacements, strict=True):
        day = original[0][:10]
        assert full.loc[day, ['open', 'high', 'low', 'close']].tolist() == expected
        assert full.loc[day, 'volume'] == original[5]
        assert entry['source'] == 'dnse' and entry['volume_source'] == 'fhsc'
        assert list(entry['original_ohlc'].values()) == list(original[1:5])
        assert list(entry['replacement_ohlc'].values()) == expected
    assert full.loc['2021-02-18', ['open', 'high', 'low', 'close', 'volume']].tolist() == list(clean_bar[1:])
    assert manifest['status'] == 'complete'


@pytest.mark.parametrize('unexpected', [
    ('2021-02-19T00:00:00Z', 1127.46, 1151.54, 1127.46, 1155.78, 459215000),
    ('2021-02-17T00:00:00Z', 1127.46, 1151.54, 1127.46, 1155.79, 459215000),
])
def test_vnindex_fails_closed_for_unreviewed_bars(stock_setup, monkeypatch, unexpected):
    stock, output, _ = stock_setup
    with pytest.raises(ValueError, match='^INVALID_OHLCV_RANGE$'):
        stock.main(historical_stock_args(output, monkeypatch, [unexpected, VNINDEX_FHSC_ROWS[-1]]))

    manifest = json.loads((output / 'manifest.json').read_text())
    assert manifest['status'] == 'failed' and manifest['files'] == []
    call = manifest['calls'][0]
    assert call['status'] == 'failed' and call['error'] == 'INVALID_OHLCV_RANGE'
    rejected = json.loads((output / call['diagnostic']).read_text())
    assert rejected['source'] == 'fhsc'
    assert [bar['date'] for bar in rejected['bars']] == [unexpected[0][:10], '2024-05-06']
    assert rejected['bars'][0]['close'] == unexpected[4]


def test_vnindex_leaves_valid_fhsc_bar_on_reviewed_day(stock_setup, monkeypatch):
    stock, output, _ = stock_setup
    improved = ('2024-05-06T00:00:00Z', 1227.25, 1241.58, 1224.22, 1241.58, 666198300)
    stock.main(historical_stock_args(output, monkeypatch, [improved, VNINDEX_FHSC_ROWS[0]]))
    full = pd.read_csv(output / 'indices/full/VNINDEX.csv').set_index('date')
    replacements = json.loads((output / 'manifest.json').read_text())['calls'][0]['replacements']
    assert full.loc['2024-05-06', 'open'] == 1227.25
    assert [entry['date'] for entry in replacements] == ['2021-02-17']


@pytest.mark.parametrize('symbol', ['FPT', 'E1VFVN30'])
def test_vnindex_replacements_do_not_apply_to_other_assets(stock_setup, monkeypatch, symbol):
    stock, output, _ = stock_setup
    with pytest.raises(ValueError, match='^INVALID_OHLCV_RANGE$'):
        stock.main(historical_stock_args(output, monkeypatch, VNINDEX_FHSC_ROWS, symbol=symbol))
    assert list(output.rglob('*.csv')) == []


def test_vn30_constituents_only_write_into_new_run(stock_setup):
    stock, output, _ = stock_setup
    assert hasattr(stock, 'main'), 'Crawler has no safe CLI'
    stock.main(['--output-root', str(output), '--start', '2026-01-01', '--end', '2026-01-02'])
    assert len((output / 'vn30_list.txt').read_text().splitlines()) == 30


def test_split_keeps_existing_boundary_overlap(stock_setup, monkeypatch):
    stock, _, _ = stock_setup
    monkeypatch.setattr(stock, 'start_date', '2023-09-29')
    monkeypatch.setattr(stock, 'end_date', '2023-10-02')
    monkeypatch.setattr(stock, 'TEST_END_DATE', '2023-10-02')
    frame = pd.DataFrame({'date': ['2023-09-29', '2023-10-01', '2023-10-02'], 'close': [1, 2, 3]})
    full, train, test = stock.split_train_test(frame)
    assert full['date'].tolist() == ['2023-09-29', '2023-10-01', '2023-10-02']
    assert train['date'].tolist() == ['2023-09-29', '2023-10-01']
    assert test['date'].tolist() == ['2023-10-01', '2023-10-02']


def test_help_works_from_other_working_directory_without_vnstock(tmp_path):
    from crawl import stock
    result = subprocess.run([sys.executable, stock.__file__, '--help'], cwd=tmp_path,
                            text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert '--output-root' in result.stdout


def test_invalid_output_is_rejected_before_provider(stock_setup):
    stock, output, calls = stock_setup
    assert hasattr(stock, 'main'), 'Crawler has no safe CLI'
    with pytest.raises(ValueError):
        stock.main(['--output-root', str(output.parents[2] / 'datasets'),
                    '--start', '2026-01-01', '--end', '2026-01-02', '--symbols', 'FPT'])
    assert calls == []


def test_stock_requires_generation_six_before_creating_output(stock_setup, monkeypatch):
    stock, output, calls = stock_setup
    monkeypatch.setattr(stock.importlib.metadata, 'version', lambda _: '4.0.4')
    with pytest.raises(ValueError):
        stock.main(['--output-root', str(output), '--start', '2026-01-01', '--end', '2026-01-02', '--symbols', 'FPT'])
    assert not output.exists()
    assert calls == []


def test_vn30_refuses_missing_provider_provenance(stock_setup, monkeypatch):
    stock, output, calls = stock_setup
    reference = sys.modules['vnstock'].Reference

    class IncompleteReference(reference):
        def constituents(self):
            frame = super().constituents()
            frame.attrs.clear()
            return frame

    monkeypatch.setattr(sys.modules['vnstock'], 'Reference', IncompleteReference)
    with pytest.raises(ValueError):
        stock.main(['--output-root', str(output), '--start', '2026-01-01', '--end', '2026-01-02'])
    assert not (output / 'vn30_list.txt').exists()
    assert calls == []
