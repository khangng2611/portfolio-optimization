import importlib
import importlib.util
import pytest

pd = pytest.importorskip('pandas', reason='Run ingestion tests in ~/.venv_6x')


def io_module():
    assert importlib.util.find_spec('crawl.vnstock_io'), 'Safe Vnstock output boundary is missing'
    return importlib.import_module('crawl.vnstock_io')


def test_output_requires_a_new_run_inside_migration_directory(tmp_path, monkeypatch):
    io = io_module()
    monkeypatch.setattr(io, 'PROJECT_ROOT', tmp_path)
    for target in [tmp_path, tmp_path / 'datasets', tmp_path / 'vnstock-migration/gen6']:
        with pytest.raises(ValueError):
            io.prepare_output(target)
    target = tmp_path / 'vnstock-migration/gen6/run1'
    assert io.prepare_output(target) == target
    with pytest.raises(FileExistsError):
        io.prepare_output(target)


def test_output_rejects_symlink_to_research_before_writing(tmp_path, monkeypatch):
    io = io_module()
    monkeypatch.setattr(io, 'PROJECT_ROOT', tmp_path)
    research = tmp_path / 'datasets'
    research.mkdir()
    (tmp_path / 'vnstock-migration').mkdir()
    (tmp_path / 'vnstock-migration/gen6').symlink_to(research, target_is_directory=True)
    with pytest.raises(ValueError):
        io.prepare_output(tmp_path / 'vnstock-migration/gen6/new')
    assert list(research.iterdir()) == []


def test_daily_dates_keep_vietnam_day_at_utc_boundary():
    io = io_module()
    dates = pd.Series(['2026-01-01T18:00:00Z', '2026-01-03T07:00:00+07:00'])
    assert io.daily_dates(dates).tolist() == ['2026-01-02', '2026-01-03']
    with pytest.raises(ValueError):
        io.daily_dates(pd.Series(['invalid']))


def test_date_window_rejects_invalid_or_reversed_dates():
    io = io_module()
    for start, end in [('yesterday', '2026-01-02'), ('2026-01-03', '2026-01-02')]:
        with pytest.raises(ValueError):
            io.date_window(start, end)
    assert io.date_window('2026-01-01', '2026-01-02') == ('2026-01-01', '2026-01-02')
    assert io.date_window('20260101', '20260102') == ('2026-01-01', '2026-01-02')


def bars():
    frame = pd.DataFrame({
        'time': ['2026-01-02T07:00:00+07:00', '2026-01-01T07:00:00+07:00'],
        'open': [26.0, 25.0], 'high': [27.0, 26.0], 'low': [25.0, 24.0],
        'close': [26.5, 25.5], 'volume': pd.array([None, 100], dtype='Int64'),
    })
    frame.attrs.update(source='fhsc', profile='v5')
    return frame


def test_bar_normalization_sorts_days_preserves_units_and_null_volume():
    frame = io_module().daily_bars(bars(), '2026-01-01', '2026-01-02')
    assert frame['time'].tolist() == ['2026-01-01', '2026-01-02']
    assert frame['close'].tolist() == [25.5, 26.5]
    assert pd.isna(frame['volume'].iloc[1])


@pytest.mark.parametrize('change', ['negative', 'duplicate', 'missing', 'outside', 'partial', 'source'])
def test_bar_normalization_refuses_invalid_or_unfinished_data(change):
    frame = bars()
    if change == 'negative':
        frame.loc[0, 'close'] = -1
    elif change == 'duplicate':
        frame.loc[0, 'time'] = frame.loc[1, 'time']
    elif change == 'missing':
        frame = frame.drop(columns='close')
    elif change == 'outside':
        frame.loc[0, 'time'] = '2026-01-04'
    elif change == 'partial':
        frame.attrs['last_bar_partial'] = True
    elif change == 'source':
        frame.attrs['source'] = 'other-provider'
    with pytest.raises(ValueError):
        io_module().daily_bars(frame, '2026-01-01', '2026-01-02')


@pytest.mark.parametrize('value', ['2026-01', 'today', 1700000000])
def test_daily_dates_do_not_invent_observation_dates(value):
    with pytest.raises(ValueError):
        io_module().daily_dates(pd.Series([value]))


@pytest.mark.parametrize('column', ['open', 'volume'])
def test_boolean_values_are_not_prices_or_volume(column):
    frame = bars()
    if column == 'open':
        frame[['open', 'high', 'low', 'close']] = True
    else:
        frame[column] = True
    with pytest.raises(ValueError):
        io_module().daily_bars(frame, '2026-01-01', '2026-01-02')


@pytest.mark.parametrize('key', ['source', 'profile'])
def test_missing_provenance_is_not_replaced_by_expected_values(key):
    frame = bars()
    frame.attrs.pop(key)
    with pytest.raises(ValueError):
        io_module().daily_bars(frame, '2026-01-01', '2026-01-02')
