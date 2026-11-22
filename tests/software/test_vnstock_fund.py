import importlib
import importlib.metadata
import socket
import sys
from types import SimpleNamespace

import pytest

from test_vnstock_crawl_io import io_module

pd = pytest.importorskip('pandas', reason='Run ingestion tests in ~/.venv_6x')


@pytest.fixture
def fund_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Network forbidden'))
    monkeypatch.setattr(io_module(), 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(importlib.metadata, 'version', lambda _: '6.0.1')
    catalog = pd.DataFrame({
        'ticker': ['VFF', 'DCDS', 'VCBF-BCF'], 'name': ['VinaCapital bond fund', 'Dynamic fund', 'Blue chip fund'],
        'organ_name': ['VinaCapital', 'Dragon Capital', 'VCBF'], 'fund_type': ['bond_fund', 'equity_fund', 'equity_fund'],
        'valuation_frequency': ['daily', 'daily', 'daily'],
    })
    catalog.attrs.update(source='fhsc', profile='v5')
    state = {'wrong_ticker': False, 'unit': 'VND/fund_unit', 'errors': [], 'calls': 0, 'profile': 'v5',
             'null_ticker': False, 'boolean_nav': False, 'missing_source': False}

    class Reference:
        def __init__(self, source=None):
            assert source == 'fhsc'
            self.fund = self

        def list(self):
            return catalog.copy()

        def __call__(self, symbol):
            self.symbol = symbol
            return self

        def profile(self):
            frame = pd.DataFrame({'ticker': ['OTHER' if state['wrong_ticker'] else self.symbol],
                                 'name': ['Fund'], 'nav': [26064.61]})
            frame.attrs.update(source='fhsc', profile='v5')
            return frame

    class Market:
        def __init__(self, source=None):
            assert source == 'fhsc'

        def fund(self, symbol):
            self.symbol = symbol
            return self

        def history(self, *, start, end, compat):
            assert (start, end, compat) == ('2026-01-01', '2026-01-02', 'v5')
            state['calls'] += 1
            if state['errors']:
                raise state['errors'].pop(0)
            nav = [26064.61, 26120.0] if self.symbol == 'VFF' else [45000.0, 45100.0]
            frame = pd.DataFrame({'time': ['2026-01-01', '2026-01-02'], 'nav': nav})
            frame.attrs.update(source='fhsc', profile=state['profile'], nav_unit=state['unit'])
            if state['null_ticker']:
                frame['ticker'] = pd.array([pd.NA, pd.NA], dtype='string')
            if state['boolean_nav']:
                frame['nav'] = True
            if state['missing_source']:
                frame.attrs.pop('source')
            return frame

    monkeypatch.setitem(sys.modules, 'vnstock', SimpleNamespace(Market=Market, Reference=Reference))
    module = importlib.import_module('crawl.fund')
    monkeypatch.setattr(module.time, 'sleep', lambda *_: None)
    return module, tmp_path / 'vnstock-migration/gen6/funds', state, catalog


def run_funds(module, output, *symbols):
    assert hasattr(module, 'main'), 'Fund crawler has no safe CLI'
    module.main(['--output-root', str(output), '--start', '2026-01-01', '--end', '2026-01-02',
                 '--symbols', *(symbols or ['VFF'])])


def test_fund_nav_uses_requested_identity_and_preserves_csv_contract(fund_setup):
    fund, output, _, _ = fund_setup
    run_funds(fund, output, 'VFF', 'DCDS')
    vff = pd.read_csv(output / 'funds/full/VFF.csv')
    dcds = pd.read_csv(output / 'funds/full/DCDS.csv')
    assert vff.columns.tolist() == ['date', 'price', 'symbol']
    assert vff['price'].tolist() == [26.06, 26.12]
    assert dcds['price'].tolist() == [45.0, 45.1]
    assert vff['symbol'].tolist() == ['VFF', 'VFF']
    assert (output / 'funds/train/VFF_train.csv').exists()
    assert (output / 'funds/test/VFF_test.csv').exists()
    assert (output / 'funds/raw/VFF.csv').exists()


@pytest.mark.parametrize('problem', ['ticker', 'issuer', 'type', 'unit'])
def test_wrong_fund_identity_or_unit_is_not_relabelled(fund_setup, problem):
    fund, output, state, catalog = fund_setup
    if problem == 'ticker':
        state['wrong_ticker'] = True
    elif problem == 'issuer':
        catalog.loc[0, 'organ_name'] = 'Other issuer'
    elif problem == 'type':
        catalog.loc[0, 'fund_type'] = 'equity_fund'
    else:
        state['unit'] = 'thousand_VND/fund_unit'
    with pytest.raises(ValueError):
        run_funds(fund, output)
    assert not (output / 'funds/full/VFF.csv').exists()


def test_auth_failure_is_not_retried_or_printed(fund_setup, capsys):
    fund, output, state, _ = fund_setup

    class AuthError(Exception):
        kind = 'auth'
        retryable = False

    state['errors'] = [AuthError('do not print credentials')]
    with pytest.raises(AuthError):
        run_funds(fund, output)
    assert state['calls'] == 1
    assert 'credentials' not in capsys.readouterr().out


def test_temporary_rate_limit_is_retried_with_a_bound(fund_setup):
    fund, output, state, _ = fund_setup

    class RateLimitError(Exception):
        kind = 'rate_limit'
        retryable = True

    state['errors'] = [RateLimitError('temporary'), RateLimitError('temporary')]
    run_funds(fund, output)
    assert state['calls'] == 3
    assert (output / 'funds/full/VFF.csv').exists()


def test_fund_list_uses_ticker_and_bond_fund_type(fund_setup):
    fund, output, _, _ = fund_setup
    run_funds(fund, output)
    assert (output / 'fund_list.txt').read_text().splitlines() == ['VFF', 'DCDS', 'VCBF-BCF']
    fund.retrieve_bond_list()
    assert (output / 'bond_list.txt').read_text().splitlines() == ['VFF']


def test_fund_requires_generation_six_before_creating_output(fund_setup, monkeypatch):
    fund, output, state, _ = fund_setup
    monkeypatch.setattr(fund.importlib.metadata, 'version', lambda _: '4.0.4')
    with pytest.raises(ValueError):
        run_funds(fund, output)
    assert not output.exists()
    assert state['calls'] == 0


def test_fund_refuses_an_unrequested_column_profile(fund_setup):
    fund, output, state, _ = fund_setup
    state['profile'] = 'v6'
    with pytest.raises(ValueError):
        run_funds(fund, output)
    assert not (output / 'funds/full/VFF.csv').exists()


def test_hyphenated_fund_ticker_is_safe_and_supported(fund_setup):
    fund, output, _, _ = fund_setup
    run_funds(fund, output, 'VCBF-BCF')
    frame = pd.read_csv(output / 'funds/full/VCBF-BCF.csv')
    assert frame['symbol'].tolist() == ['VCBF-BCF', 'VCBF-BCF']


@pytest.mark.parametrize('problem', ['null_ticker', 'boolean_nav', 'missing_source'])
def test_invalid_nav_or_identity_cannot_be_exported(fund_setup, problem):
    fund, output, state, _ = fund_setup
    state[problem] = True
    with pytest.raises(ValueError):
        run_funds(fund, output)
    assert not (output / 'funds/full/VFF.csv').exists()


def test_unverified_future_version_cannot_reuse_nav_unit_contract(fund_setup, monkeypatch):
    fund, output, state, _ = fund_setup
    monkeypatch.setattr(fund.importlib.metadata, 'version', lambda _: '6.9.0')
    with pytest.raises(ValueError):
        run_funds(fund, output)
    assert not output.exists()
    assert state['calls'] == 0


@pytest.mark.parametrize('fund_type', [None, 'unknown'])
def test_selected_fund_requires_valid_catalog_identity(fund_setup, fund_type):
    fund, output, _, catalog = fund_setup
    catalog.loc[1, 'fund_type'] = fund_type
    with pytest.raises(ValueError):
        run_funds(fund, output, 'VFF', 'DCDS')
    assert (output / 'funds/full/VFF.csv').exists()
    assert not (output / 'funds/full/DCDS.csv').exists()
