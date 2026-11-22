"""Fetch a bounded FHSC stock pack into a new migration run, without research writes.

Price basis stays unverified unless the provider attests all OHLC columns are adjusted.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawl.vnstock_io import SOURCE, check_identity, daily_bars, date_window, prepare_output, symbol_id


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbols', nargs='+', required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    if not 2 <= len(args.symbols) <= 20 or len(set(args.symbols)) != len(args.symbols):
        raise ValueError('Two to twenty distinct stock symbols required')
    for symbol in args.symbols:
        symbol_id(symbol)
    start, end = date_window(args.start, args.end)
    version = importlib.metadata.version('vnstock')
    if not version.startswith('6.'):
        raise ValueError('This fetch adapter requires vnstock 6')
    root = prepare_output(args.output)
    from vnstock import Market

    files = []
    for symbol in args.symbols:
        raw = Market(SOURCE).equity(symbol).ohlcv(
            start=start, end=end, interval='1D', count_back=5000, compat='v5',
        )
        check_identity(raw, symbol)
        frame = daily_bars(raw, start, end)
        basis = raw.attrs.get('column_basis', {})
        adjusted = all(basis.get(column) == 'adjusted' for column in ['open', 'high', 'low', 'close'])
        path = root / f'{symbol}.csv'
        frame.to_csv(path, index=False, mode='x')
        files.append({
            'asset_id': symbol, 'file': path.name,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'row_count': len(frame), 'first_date': frame['time'].min(), 'last_date': frame['time'].max(),
            'actual_provider': raw.attrs.get('source', SOURCE),
            'column_basis': basis, 'price_basis': 'provider_adjusted' if adjusted else 'unverified',
            'profile': raw.attrs.get('profile', 'v5'),
            'schema_changes': raw.attrs.get('schema_changes', []),
        })
        print(f'{symbol}: {len(frame)} daily bars, latest {files[-1]["last_date"]}', flush=True)
    manifest = {
        'schema_version': 1, 'data_origin': 'real', 'requested_provider': SOURCE,
        'library': 'vnstock', 'library_version': version,
        'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'requested_start': start, 'requested_end': end,
        'source_unit': 'thousand_VND/share', 'csv_origin': 'vnstock_normalized',
        'price_basis': 'provider_adjusted' if all(f['price_basis'] == 'provider_adjusted' for f in files) else 'unverified',
        'documentation': 'https://vnstocks.com/docs/vnstock/v6/thi-truong-market', 'files': files,
    }
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'FAILED: {type(exc).__name__}', file=sys.stderr)
        raise SystemExit(1) from None
