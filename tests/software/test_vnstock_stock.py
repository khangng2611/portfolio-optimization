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
