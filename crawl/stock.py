"""Fetch FHSC stock/ETF/index bars into a new migration run, never research datasets."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import TRAIN_START_DATE, SPLIT_DATE
from crawl.vnstock_io import (
    OHLC_COLUMNS, SOURCE, check_identity, daily_bars, daily_dates, date_window,
    invalid_ohlc_range, numeric_values, prepare_output, symbol_id,
)

START_INDEX = 0
BATCH_SIZE = 10
start_date = TRAIN_START_DATE
end_date = None
TEST_END_DATE = None
DATASETS_DIR = None
LIST_FILE = None
OUTPUT_DIR = None
INDEX_OUTPUT_DIR = None
_provenance = []

# shortcut: reviewed historical OHLC only, add another signature after independent verification.
VNINDEX_OHLC_REPLACEMENTS = {
    '2021-02-17': ((1127.46, 1151.54, 1127.46, 1155.78), (1127.46, 1155.78, 1127.46, 1155.78)),
    '2021-12-10': ((1469.83, 1475.85, 1469.68, 1463.54), (1470.55, 1475.85, 1461.78, 1463.54)),
    '2023-05-15': ((1074.82, 1076.32, 1067.15, 1065.71), (1074.82, 1076.32, 1065.71, 1065.71)),
    '2024-05-06': ((1226.89, 1226.89, 1224.22, 1241.58), (1226.89, 1241.58, 1224.22, 1241.58)),
}
VNINDEX_REPLACEMENT_EVIDENCE = {
    'feed': 'DNSE Entrade X',
    'url': 'https://services.entrade.com.vn/chart-api/v2/ohlcs/index?from=1613408400&to=1715187600&symbol=VNINDEX&resolution=1D',
    'response_sha256': '9ccdf282738e8280ec74228883470f8ac21c7c5dc8c66a9ac947507318c02e66',
    'retrieved_at': '2026-11-22T20:49:54.579183+07:00',
    'verification': 'Daily OHLC cross-checked against the same-day DNSE 1-minute bars.',
}


def retrieve_vn30_list():
    from vnstock import Reference

    members = Reference(SOURCE).index('VN30').constituents()
    if members.attrs.get('source') != SOURCE or members.attrs.get('profile') != 'v5':
        raise ValueError('UNEXPECTED_VN30_SOURCE_OR_PROFILE')
    symbols = [symbol_id(value) for value in members['symbol']]
    if len(symbols) != 30 or len(set(symbols)) != 30:
        raise ValueError('INVALID_VN30_CONSTITUENTS')
    with LIST_FILE.open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(symbols) + '\n')
    return symbols


def split_train_test(df):
    frame = df.copy()
    frame['date'] = daily_dates(frame['date'])
    if frame['date'].duplicated().any():
        raise ValueError('DUPLICATE_DAILY_DATE')
    frame = frame.sort_values('date')
    full = frame[frame['date'].between(start_date, end_date)].copy()
    return full, full[full['date'] <= SPLIT_DATE].copy(), full[full['date'] >= SPLIT_DATE].copy()


def _reconcile_vnindex(raw, provenance):
    frame = raw.reset_index(drop=True)
    dates = daily_dates(frame['time'])
    prices = frame[OHLC_COLUMNS].apply(numeric_values)
    rejected = invalid_ohlc_range(prices)
    corrected = prices.astype(float)
    replacements = []
    for idx in prices.index[rejected]:
        day = dates.at[idx]
        rule = VNINDEX_OHLC_REPLACEMENTS.get(day)
        if rule is None or tuple(prices.loc[idx]) != rule[0]:
            continue
        original, replacement = rule
        corrected.loc[idx] = replacement
        replacements.append({
            'date': day, 'source': 'dnse', 'volume_source': SOURCE,
            'original_ohlc': dict(zip(OHLC_COLUMNS, original)),
            'replacement_ohlc': dict(zip(OHLC_COLUMNS, replacement)),
        })
    try:
        validated = daily_bars(frame.assign(**corrected), start_date, end_date)
    except ValueError as exc:
        diagnostic = DATASETS_DIR / 'diagnostics/VNINDEX-ohlc-rejected.json'
        diagnostic.parent.mkdir(exist_ok=True)
        bars = frame.assign(date=dates, **prices).loc[rejected, ['date', *OHLC_COLUMNS, 'volume']]
        diagnostic.write_text(json.dumps({
            'symbol': 'VNINDEX', 'source': SOURCE, 'start': start_date, 'end': end_date,
            'error': str(exc), 'bars': json.loads(bars.to_json(orient='records')),
        }, indent=2) + '\n')
        _provenance.append({**provenance, 'status': 'failed', 'error': str(exc),
                            'diagnostic': diagnostic.relative_to(DATASETS_DIR).as_posix()})
        raise
    provenance.update(replacements=sorted(replacements, key=lambda bar: bar['date']),
                      replacement_evidence=VNINDEX_REPLACEMENT_EVIDENCE)
    return validated


def _fetch_and_save(symbol, kind):
    symbol_id(symbol)
    if DATASETS_DIR is None:
        raise ValueError('OUTPUT_NOT_CONFIGURED_USE_CLI')
    from vnstock import Market

    raw = getattr(Market(SOURCE), kind)(symbol).ohlcv(
        start=start_date, end=end_date, interval='1D', compat='v5',
    )
    check_identity(raw, symbol)
    provenance = {
        'symbol': symbol, 'route': f'market.{kind}.ohlcv', 'source': raw.attrs.get('source', SOURCE),
        'profile': raw.attrs.get('profile', 'v5'), 'schema_changes': raw.attrs.get('schema_changes', []),
        'column_basis': raw.attrs.get('column_basis', {}),
    }
    try:
        validated = daily_bars(raw, start_date, end_date)
    except ValueError as exc:
        if kind != 'index' or symbol != 'VNINDEX' or str(exc) != 'INVALID_OHLCV_RANGE':
            raise
        validated = _reconcile_vnindex(raw, provenance)
    frame = validated.rename(columns={'time': 'date'})
    frame['symbol'] = symbol
    provenance.update({
        'row_count': len(frame),
        'first_date': frame['date'].min(), 'last_date': frame['date'].max(),
    })
    directory = INDEX_OUTPUT_DIR if kind == 'index' else OUTPUT_DIR
    for part, values in zip(['full', 'train', 'test'], split_train_test(frame)):
        target = directory / part
        target.mkdir(parents=True, exist_ok=True)
        suffix = '' if part == 'full' else f'_{part}'
        values.to_csv(target / f'{symbol}{suffix}.csv', index=False, encoding='utf-8-sig', mode='x')
    _provenance.append(provenance)
    return True


def fetch_and_save(symbol):
    return _fetch_and_save(symbol, 'etf' if symbol == 'E1VFVN30' else 'equity')


def fetch_and_save_index(symbol='VNINDEX'):
    return _fetch_and_save(symbol, 'index')


def retrieve_ohlcv_for_vn30_symbols():
    symbols = LIST_FILE.read_text(encoding='utf-8').splitlines()[START_INDEX:START_INDEX + BATCH_SIZE]
    for symbol in symbols:
        fetch_and_save(symbol)
        time.sleep(1.2)


def _write_manifest(status):
    files = [{'file': str(path.relative_to(DATASETS_DIR)),
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in sorted(DATASETS_DIR.rglob('*.csv'))]
    (DATASETS_DIR / 'manifest.json').write_text(json.dumps({
        'library': 'vnstock', 'library_version': importlib.metadata.version('vnstock'),
        'requested_provider': SOURCE, 'profile': 'v5', 'start': start_date, 'end': end_date,
        'retrieved_at': datetime.now(timezone.utc).isoformat(), 'status': status, 'calls': _provenance,
        'stock_unit': 'thousand_VND/share', 'index_unit': 'point', 'files': files,
        'documentation': 'https://vnstocks.com/docs/vnstock/v6/thi-truong-market',
    }, indent=2) + '\n')


def main(argv=None):
    global DATASETS_DIR, LIST_FILE, OUTPUT_DIR, INDEX_OUTPUT_DIR, start_date, end_date, TEST_END_DATE, _provenance
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--symbols', nargs='+')
    parser.add_argument('--index')
    args = parser.parse_args(argv)
    start_date, end_date = date_window(args.start, args.end)
    TEST_END_DATE = end_date
    for symbol in (args.symbols or []) + ([args.index] if args.index else []):
        symbol_id(symbol)
    if not importlib.metadata.version('vnstock').startswith('6.'):
        raise ValueError('VNSTOCK6_REQUIRED')
    DATASETS_DIR = prepare_output(args.output_root)
    _provenance = []
    LIST_FILE = DATASETS_DIR / 'vn30_list.txt'
    OUTPUT_DIR = DATASETS_DIR / 'stocks'
    INDEX_OUTPUT_DIR = DATASETS_DIR / 'indices'
    if not args.symbols and not args.index:
        retrieve_vn30_list()
        retrieve_ohlcv_for_vn30_symbols()
    for symbol in args.symbols or []:
        fetch_and_save(symbol)
        time.sleep(1.2)
    status = 'failed'
    try:
        if args.index:
            fetch_and_save_index(args.index)
        status = 'complete'
    finally:
        _write_manifest(status)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'FAILED: {type(exc).__name__}', file=sys.stderr)
        raise SystemExit(1) from None
