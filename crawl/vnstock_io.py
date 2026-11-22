"""Shared FHSC ingestion boundaries; research inputs are never output targets."""

from datetime import date
from math import isfinite
from pathlib import Path
import re

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'fhsc'


def prepare_output(output: str | Path) -> Path:
    allowed = PROJECT_ROOT.resolve() / 'vnstock-migration/gen6'
    target = Path(output).resolve()
    if target == allowed or not target.is_relative_to(allowed):
        raise ValueError('OUTPUT_MUST_BE_A_NEW_MIGRATION_RUN')
    target.mkdir(parents=True, exist_ok=False)
    return target


def date_window(start: str, end: str) -> tuple[str, str]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ValueError('INVALID_DATE_WINDOW')
    return first.isoformat(), last.isoformat()


def symbol_id(symbol: str) -> str:
    if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z0-9]{1,12}', symbol):
        raise ValueError('INVALID_SYMBOL')
    return symbol


def fund_id(symbol: str) -> str:
    if (not isinstance(symbol, str) or len(symbol) > 32
            or not re.fullmatch(r'[A-Z0-9]+(?:-[A-Z0-9]+)*', symbol)):
        raise ValueError('INVALID_FUND_SYMBOL')
    return symbol


def daily_dates(values: pd.Series) -> pd.Series:
    def day(value):
        if pd.isna(value) or not isinstance(value, (str, date, np.datetime64)):
            raise ValueError('INVALID_DAILY_DATE')
        if isinstance(value, str) and not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[T ][0-9].*)?', value):
            raise ValueError('INVALID_DAILY_DATE')
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is not None:
            stamp = stamp.tz_convert('Asia/Ho_Chi_Minh')
        return stamp.strftime('%Y-%m-%d')

    return values.map(day)


def numeric_values(values: pd.Series) -> pd.Series:
    if values.map(lambda value: isinstance(value, (bool, np.bool_))).any():
        raise ValueError('BOOLEAN_IS_NOT_A_NUMERIC_OBSERVATION')
    return pd.to_numeric(values, errors='raise')


def check_identity(frame: pd.DataFrame, symbol: str) -> None:
    for column in ['symbol', 'ticker']:
        if column in frame and (frame[column].isna().any() or not frame[column].eq(symbol).all()):
            raise ValueError('SOURCE_SYMBOL_MISMATCH')


def daily_bars(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    start, end = date_window(start, end)
    columns = ['time', 'open', 'high', 'low', 'close', 'volume']
    if frame.empty or not set(columns) <= set(frame.columns):
        raise ValueError('INVALID_OHLCV_COLUMNS')
    if frame.attrs.get('last_bar_partial') or frame.attrs.get('truncated'):
        raise ValueError('INCOMPLETE_OHLCV')
    if frame.attrs.get('source') != SOURCE or frame.attrs.get('profile') != 'v5':
        raise ValueError('UNEXPECTED_SOURCE_OR_PROFILE')
    result = frame[columns].copy()
    result['time'] = daily_dates(result['time'])
    if result['time'].duplicated().any() or not result['time'].between(start, end).all():
        raise ValueError('INVALID_OHLCV_DAYS')
    for column in ['open', 'high', 'low', 'close']:
        result[column] = numeric_values(result[column])
        if not result[column].map(lambda value: isfinite(value) and value > 0).all():
            raise ValueError('INVALID_OHLCV_PRICE')
    if (result['high'] < result[['open', 'low', 'close']].max(axis=1)).any() or (
        result['low'] > result[['open', 'high', 'close']].min(axis=1)
    ).any():
        raise ValueError('INVALID_OHLCV_RANGE')
    volume = numeric_values(result['volume'])
    if not volume.dropna().map(lambda value: isfinite(value) and value >= 0 and value % 1 == 0).all():
        raise ValueError('INVALID_OHLCV_VOLUME')
    result['volume'] = volume.astype('Int64')
    return result.sort_values('time').reset_index(drop=True)
