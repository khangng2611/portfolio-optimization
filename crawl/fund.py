"""Fetch identity-checked FHSC fund NAV into a new migration run."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import TRAIN_START_DATE, SPLIT_DATE
from crawl.vnstock_io import SOURCE, check_identity, daily_dates, date_window, fund_id, numeric_values, prepare_output

START_INDEX = 0
BATCH_SIZE = 10
DATASETS_DIR = None
LIST_FILE = None
BOND_LIST_FILE = None
OUTPUT_DIR = None
start_date = TRAIN_START_DATE
end_date = None
_catalog = None
_provenance = []
# Pinned 6.0.1 contract: market.fund.history reads fhsc value_unit='dong', no v5 scale.
NAV_UNIT = 'VND/fund_unit'


def retrieve_fund_list():
    global _catalog
    from vnstock import Reference

    frame = Reference(SOURCE).fund.list()
    if frame.empty or not {'ticker', 'fund_type', 'organ_name'} <= set(frame.columns):
        raise ValueError('INVALID_FUND_CATALOG')
    if frame.attrs.get('source') != SOURCE or frame.attrs.get('profile') != 'v5':
        raise ValueError('UNEXPECTED_FUND_CATALOG_SOURCE_OR_PROFILE')
    symbols = [fund_id(value) for value in frame['ticker']]
    if len(set(symbols)) != len(symbols):
        raise ValueError('AMBIGUOUS_FUND_CATALOG')
    with LIST_FILE.open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(symbols) + '\n')
    _catalog = frame.copy()
    return symbols


def retrieve_bond_list():
    if _catalog is None:
        retrieve_fund_list()
    types = _catalog['fund_type']
    if not types.isin(['bond_fund', 'equity_fund', 'balanced_fund']).all():
        raise ValueError('UNKNOWN_FUND_TYPE')
    symbols = _catalog.loc[types == 'bond_fund', 'ticker'].tolist()
    with BOND_LIST_FILE.open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(symbols) + '\n')
    return symbols


def get_nav_and_return(symbol):
    fund_id(symbol)
    if OUTPUT_DIR is None or _catalog is None:
        raise ValueError('OUTPUT_NOT_CONFIGURED_USE_CLI')
    if importlib.metadata.version('vnstock') != '6.0.1':
        raise ValueError('UNVERIFIED_NAV_UNIT_CONTRACT_VERSION')
    from vnstock import Market, Reference

    identity = _catalog[_catalog['ticker'] == symbol]
    profile = Reference(SOURCE).fund(symbol).profile()
    if len(identity) != 1 or len(profile) != 1 or 'ticker' not in profile:
        raise ValueError('FUND_IDENTITY_MISMATCH')
    kind, issuer = identity.iloc[0]['fund_type'], identity.iloc[0]['organ_name']
    if (not isinstance(kind, str) or kind not in {'bond_fund', 'equity_fund', 'balanced_fund'}
            or not isinstance(issuer, str) or not issuer.strip()):
        raise ValueError('INCOMPLETE_FUND_IDENTITY')
    check_identity(profile, symbol)
    if profile.attrs.get('source') != SOURCE or profile.attrs.get('profile') != 'v5':
        raise ValueError('UNEXPECTED_FUND_PROFILE_SOURCE_OR_PROFILE')
    if symbol == 'VFF' and (
        identity.iloc[0]['fund_type'] != 'bond_fund'
        or 'VINACAPITAL' not in str(identity.iloc[0]['organ_name']).upper().replace(' ', '')
    ):
        raise ValueError('VFF_IDENTITY_MISMATCH')
    for attempt in range(3):
        try:
            raw = Market(SOURCE).fund(symbol).history(start=start_date, end=end_date, compat='v5')
            break
        except Exception as exc:
            if attempt == 2 or getattr(exc, 'kind', None) not in {'rate_limit', 'network'} or not getattr(exc, 'retryable', False):
                raise
            time.sleep(2 ** attempt)
    if raw.empty or not {'time', 'nav'} <= set(raw.columns):
        raise ValueError('INVALID_FUND_NAV_COLUMNS')
    if (raw.attrs.get('source') != SOURCE or raw.attrs.get('nav_unit', NAV_UNIT) != NAV_UNIT
            or raw.attrs.get('profile') != 'v5'):
        raise ValueError('UNEXPECTED_FUND_SOURCE_OR_UNIT')
    if raw.attrs.get('truncated'):
        raise ValueError('INCOMPLETE_FUND_HISTORY')
    check_identity(raw, symbol)
    frame = pd.DataFrame({'date': daily_dates(raw['time']), 'price': numeric_values(raw['nav'])})
    if frame['price'].isna().any() or not frame['price'].map(lambda x: 0 < x < float('inf')).all():
        raise ValueError('INVALID_FUND_NAV')
    if frame['date'].duplicated().any() or not frame['date'].between(start_date, end_date).all():
        raise ValueError('INVALID_FUND_DAYS')
    _provenance.append({
        'symbol': symbol, 'profile_ticker': profile.iloc[0]['ticker'],
        'route': 'market.fund.history', 'source': raw.attrs.get('source', SOURCE),
        'profile': raw.attrs.get('profile', 'v5'), 'schema_changes': raw.attrs.get('schema_changes', []),
        'nav_unit': NAV_UNIT, 'row_count': len(frame),
        'first_date': frame['date'].min(), 'last_date': frame['date'].max(),
    })
    target = OUTPUT_DIR / 'raw'
    target.mkdir(parents=True, exist_ok=True)
    raw[['time', 'nav']].to_csv(target / f'{symbol}.csv', index=False, mode='x')
    frame['price'] = (frame['price'] / 1000).round(2)
    frame['symbol'] = symbol
    return frame.sort_values('date').reset_index(drop=True)


def split_train_test(df):
    frame = df.copy()
    frame['date'] = daily_dates(frame['date'])
    if frame['date'].duplicated().any():
        raise ValueError('DUPLICATE_DAILY_DATE')
    full = frame[frame['date'].between(start_date, end_date)].sort_values('date').copy()
    return full, full[full['date'] <= SPLIT_DATE].copy(), full[full['date'] >= SPLIT_DATE].copy()


def crawl_fund_nav_history(symbols=None):
    selected = symbols if symbols is not None else _catalog['ticker'].tolist()[START_INDEX:START_INDEX + BATCH_SIZE]
    for symbol in selected:
        frame = get_nav_and_return(symbol)
        for part, values in zip(['full', 'train', 'test'], split_train_test(frame)):
            target = OUTPUT_DIR / part
            target.mkdir(parents=True, exist_ok=True)
            suffix = '' if part == 'full' else f'_{part}'
            values.to_csv(target / f'{symbol}{suffix}.csv', index=False, encoding='utf-8-sig', mode='x')
        time.sleep(1.5)


def main(argv=None):
    global DATASETS_DIR, LIST_FILE, BOND_LIST_FILE, OUTPUT_DIR, start_date, end_date, _catalog, _provenance
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--symbols', nargs='+')
    args = parser.parse_args(argv)
    start_date, end_date = date_window(args.start, args.end)
    for symbol in args.symbols or []:
        fund_id(symbol)
    if importlib.metadata.version('vnstock') != '6.0.1':
        raise ValueError('UNVERIFIED_NAV_UNIT_CONTRACT_VERSION')
    DATASETS_DIR = prepare_output(args.output_root)
    LIST_FILE = DATASETS_DIR / 'fund_list.txt'
    BOND_LIST_FILE = DATASETS_DIR / 'bond_list.txt'
    OUTPUT_DIR = DATASETS_DIR / 'funds'
    _catalog = None
    _provenance = []
    retrieve_fund_list()
    crawl_fund_nav_history(args.symbols)
    files = [{'file': str(path.relative_to(DATASETS_DIR)),
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in sorted(DATASETS_DIR.rglob('*.csv'))]
    (DATASETS_DIR / 'manifest.json').write_text(json.dumps({
        'library': 'vnstock', 'library_version': importlib.metadata.version('vnstock'),
        'requested_provider': SOURCE, 'profile': 'v5', 'start': start_date, 'end': end_date,
        'retrieved_at': datetime.now(timezone.utc).isoformat(), 'calls': _provenance,
        'nav_unit': NAV_UNIT, 'output_unit': 'thousand_VND/fund_unit', 'files': files,
        'identity': _catalog[_catalog['ticker'].isin(args.symbols or _catalog['ticker'])].to_dict('records'),
        'documentation': 'https://vnstocks.com/docs/vnstock/v6/thi-truong-market',
    }, indent=2, default=str) + '\n')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'FAILED: {type(exc).__name__}', file=sys.stderr)
        raise SystemExit(1) from None
