"""Retrospective walk-forward forecasts for the frozen SJC–K5 study."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

HERE = Path(__file__).resolve().parent
FROZEN = HERE.parent / 'extensions_C_v1'
BASELINE = (HERE.parent / 'outputs/step1/readiness_20261012/runs'
            / 'availability-observed-contract-20261012T233110')
TZ = 'Asia/Ho_Chi_Minh'
HORIZON = 5
VIEWS = ('gold', 'derived', 'direct')


def check_ledger(eligible, ledger):
    """Match each feature input to a ledger observation known by that session's cutoff."""
    ledger = ledger.copy()
    for col in ('observed_at', 'available_at', 'decision_at'):
        ledger[col] = pd.to_datetime(ledger[col], utc=True)
    expected_cutoffs = (ledger.session_date.dt.tz_localize(TZ) + pd.Timedelta(hours=18)).dt.tz_convert('UTC')
    if not (ledger.observed_at.le(ledger.available_at) & ledger.available_at.le(ledger.decision_at)
            & ledger.decision_at.eq(expected_cutoffs)).all():
        raise ValueError('Observation or publication after cutoff, or wrong session cutoff')
    prices = ledger.pivot(index='session_date', columns='asset', values='price')
    pd.testing.assert_frame_equal(eligible, prices.loc[eligible.index, eligible.columns], check_names=False,
                                  check_exact=True)


def build_panel(eligible, valuation, history, split):
    dates = eligible.index
    if (not dates.is_unique or not dates.is_monotonic_increasing or not dates.equals(valuation.index)
            or not eligible.columns.equals(valuation.columns)):
        raise ValueError('Frozen price panels are misaligned')
    for frame in (eligible, valuation):
        if not (np.isfinite(frame) & frame.gt(0)).all().all():
            raise ValueError('Invalid frozen price')
    history = history.loc[history.experiment_id.eq('A3_ProposedK5')].sort_values('selection_date')
    if (history.empty or not history.selection_date.is_unique
            or not history.history_end.lt(history.selection_date).all()
            or not history.selection_date.isin(dates).all()):
        raise ValueError('Invalid history for point-in-time A3 membership')
    assets = eligible.columns
    selections = [tuple(json.loads(value)) for value in history.selected_assets]
    if any(len(set(s)) != 5 or len(s) != 5 or not set(s) <= set(assets) - {'GOLD', 'VFF'}
           for s in selections):
        raise ValueError('Invalid K5 constituents')
    selection_indices = history.selection_date.searchsorted(dates, side='right') - 1
    members = [selections[s] if s >= 0 else () for s in selection_indices]
    periods = pd.Series(dates, index=dates)
    alignment = pd.DataFrame({
        'selection_date': [history.selection_date.iloc[s] if s >= 0 else pd.NaT for s in selection_indices],
        'k5': [','.join(s) for s in members],
        'cutoff_at': (dates.tz_localize(TZ) + pd.Timedelta(hours=18)).tz_convert('UTC'),
        'label_start': periods.shift(-1), 'label_end': periods.shift(-(HORIZON + 1))
    }, index=dates)
    # GOLD valuation closes are eligible the next calendar day; use this common
    # (conservative for equities) availability for all three matched forecasts.
    alignment['label_available_at'] = (alignment.label_end.dt.tz_localize(TZ)
                                       + pd.Timedelta(days=1)).dt.tz_convert('UTC')
    alignment['crosses_split'] = (dates <= split) & (alignment.label_end > split)
    returns = eligible.pct_change(fill_method=None)
    momentum5 = eligible.pct_change(5, fill_method=None)
    momentum20 = eligible.pct_change(20, fill_method=None)
    vol = returns.rolling(20).std()
    features = {a: np.column_stack((momentum5[a], momentum20[a], vol[a]))
                for a in assets if a != 'VFF'}
    targets = (valuation.shift(-(HORIZON + 1)) / valuation.shift(-1) - 1).drop(columns='VFF')
    values = eligible.to_numpy()
    basket = np.full((len(dates), 3), np.nan)
    basket_label = np.full(len(dates), np.nan)
    for i, names in enumerate(members):
        if i < 20 or not names:
            continue
        cols = assets.get_indexer(names)
        window = values[i-20:i+1, cols]
        capital = (window / window[0]).mean(axis=1)
        basket[i] = ((window[-1] / window[-6] - 1).mean(), capital[-1] - 1,
                     np.std(capital[1:] / capital[:-1] - 1, ddof=1))
        basket_label[i] = targets.iloc[i].loc[list(names)].to_numpy().mean()
    features['direct'] = np.column_stack((features['GOLD'], basket))
    targets['K5'] = basket_label
    targets['direct'] = targets.GOLD - targets.K5
    targets.loc[~alignment.label_available_at.le(alignment.cutoff_at.iloc[-1])] = np.nan
    for j, col in enumerate(['momentum5', 'momentum20', 'volatility20']):
        alignment['gold_' + col] = features['GOLD'][:, j]
        alignment['k5_' + col] = basket[:, j]
    alignment['gold_actual'] = targets.GOLD
    alignment['k5_actual'] = targets.K5
    alignment['spread_actual'] = targets.direct
    return alignment, members, features, targets


def training_origins(alignment, fit_index):
    ready = (alignment.label_available_at.le(alignment.cutoff_at.iloc[fit_index])
             & ~alignment.crosses_split & alignment.k5_volatility20.notna())
    return np.flatnonzero(ready)


def calibration(history, cutoff):
    past = [r for r in history if pd.notna(r['prediction']) and pd.notna(r['actual'])
            and not r['crosses_split'] and r['label_available_at'] <= cutoff]
    result = dict(calibration_n=len(past), calibration_last_origin=pd.NaT,
                  calibration_last_label_available_at=pd.NaT, calibration_mse_daily=np.nan,
                  calibration_variance_daily=np.nan, confidence=np.nan)
    if not past:
        return result
    result.update(calibration_last_origin=past[-1]['date'],
                  calibration_last_label_available_at=past[-1]['label_available_at'])
    actual = np.array([r['actual'] for r in past]) / HORIZON
    prediction = np.array([r['prediction'] for r in past]) / HORIZON
    mse = np.mean((actual - prediction) ** 2)
    variance = np.var(actual, ddof=0)
    result.update(calibration_mse_daily=mse, calibration_variance_daily=variance)
    if len(past) >= 20 and variance + mse > 0:
        result['confidence'] = np.clip(variance / (variance + mse), .1, .9)
    return result


def walk_forward(alignment, members, features, targets, calendar, settings):
    dates = alignment.index
    records = {view: [] for view in VIEWS}
    seed_predictions, fits = [], []
    cached_anchor, models = None, {}
    origins = np.array([], dtype=int)
    anchor, step = settings['anchor_index'], settings['frequency']
    hyper = {k: settings[k] for k in ('n_estimators', 'max_depth', 'learning_rate', 'subsample', 'n_jobs')}
    for event in calendar.itertuples():
        i = event.decision_index
        date = dates[i]
        info = alignment.iloc[i]
        if (date != event.decision_date or event.assumed_execution_date != dates[i+1]
                or event.selection_state_id != info.selection_date or not members[i]):
            raise ValueError('Decision calendar and dated selection or execution disagree')
        fit = anchor + (i - anchor) // step * step if i >= anchor else None
        if cached_anchor != fit:
            cached_anchor, models = fit, {}
            origins = training_origins(alignment, fit)
        enough = fit is not None and len(origins) >= settings['minimum_rows']
        raw = {v: np.nan for v in VIEWS}
        if enough:
            estimates = {}
            for key in ('GOLD', 'direct', *members[i]):
                if key not in models:
                    rows, labels = features[key][origins], targets[key].to_numpy()[origins]
                    if not np.isfinite(rows).all() or not np.isfinite(labels).all():
                        raise ValueError('Invalid training sample within eligible set')
                    models[key] = [XGBRegressor(**hyper, random_state=seed,
                                                objective='reg:squarederror').fit(rows, labels)
                                   for seed in settings['seeds']]
                    fits.append(dict(model=key, fit_date=dates[fit], first_used=date,
                                     cutoff_at=alignment.cutoff_at.iloc[fit], training_rows=len(origins),
                                     training_first_origin=dates[origins[0]], training_last_origin=dates[origins[-1]],
                                     training_last_label_end=alignment.label_end.iloc[origins[-1]],
                                     training_last_label_available_at=alignment.label_available_at.iloc[origins[-1]]))
                estimates[key] = []
                for seed, model in zip(settings['seeds'], models[key]):
                    value = float(model.predict(features[key][i:i+1])[0])
                    estimates[key].append(value)
                    seed_predictions.append(dict(date=date, model=key, seed=seed, fit_date=dates[fit],
                                                 prediction=value, actual=targets[key].iat[i]))
            raw = dict(gold=np.mean(estimates['GOLD']), direct=np.mean(estimates['direct']),
                       derived=np.mean(estimates['GOLD']) - np.mean([estimates[a] for a in members[i]]))
        lineage = dict(fit_date=dates[fit] if fit is not None else pd.NaT,
                       training_rows=len(origins) if fit is not None else 0,
                       training_last_origin=dates[origins[-1]] if enough else pd.NaT,
                       training_last_label_available_at=alignment.label_available_at.iloc[origins[-1]] if enough else pd.NaT)
        for view in VIEWS:
            audit = calibration(records[view], info.cutoff_at)
            conf = audit['confidence']
            records[view].append(dict(
                date=date, view=view, issuance='retrospective_reconstruction', prediction=raw[view], actual=targets['GOLD' if view=='gold' else 'direct'].iat[i],
                q_daily=raw[view] / HORIZON if pd.notna(conf) else np.nan, **audit, **lineage,
                **info[['cutoff_at','label_start','label_end','label_available_at','crosses_split',
                        'selection_date','k5']].to_dict(),
                status=('fit_warmup' if not enough else 'calibration_warmup' if pd.isna(conf) else 'active')))
    rows = pd.DataFrame([r for hist in records.values() for r in hist]).sort_values(['date', 'view'])
    return rows, pd.DataFrame(seed_predictions), pd.DataFrame(fits)


def equity_error_diagnostics(rows, seed_predictions, valuation, split):
    """Compare per-event mean stock errors with each additional view, recording both horizons."""
    per_name = seed_predictions.loc[~seed_predictions.model.isin(['GOLD','direct'])].groupby(
        ['date','model'])[['prediction','actual']].mean()
    origins = json.loads((BASELINE / 'views_history.json').read_text())
    native = pd.read_csv(BASELINE / 'artifacts/ml_prediction_audit.csv',
                         parse_dates=['feature_date','label_start']).set_index(['feature_date','asset'])
    per_name['aligned_equity_error'] = per_name.prediction - per_name.actual
    per_name['b2_native_error'] = np.nan
    per_name['b2_native_outcome'] = np.nan
    per_name['b2_raw_prediction'] = np.nan
    per_name['b2_native_start'] = pd.NaT
    per_name['b2_native_end'] = pd.NaT
    native_targets = valuation.shift(-HORIZON) / valuation - 1
    for event in origins:
        date, origin = pd.Timestamp(event['date']), pd.Timestamp(event['prediction_origin_date'])
        for name in event['view_names']:
            if not name.endswith('_ml_xgboost'):
                continue
            asset = name.removesuffix('_ml_xgboost')
            key = (date, asset)
            if key not in per_name.index:
                continue
            source = native.loc[(origin,asset)]
            if source.label_start != origin or source.prediction_horizon != HORIZON or origin >= date:
                raise ValueError('Unexpected native B2 prediction origin or horizon')
            ix = valuation.index.get_loc(origin) + HORIZON
            per_name.loc[key, 'b2_native_start'] = origin
            per_name.loc[key, 'b2_raw_prediction'] = source.prediction_mean
            if ix < len(valuation):
                actual = native_targets.at[origin,asset]
                per_name.loc[key, 'b2_native_end'] = valuation.index[ix]
                per_name.loc[key, 'b2_native_outcome'] = actual
                per_name.loc[key, 'b2_native_error'] = source.prediction_mean - actual
    errors = per_name.groupby(level='date')[['aligned_equity_error','b2_native_error']].mean()
    compared = rows.loc[(rows.date > split) & ~rows.crosses_split].copy()
    compared['view_error'] = compared.prediction - compared.actual
    compared = compared.pivot(index='date',columns='view',values='view_error').join(errors)
    correlations = []
    for view in VIEWS:
        for other in ['aligned_equity_error','b2_native_error', *[v for v in VIEWS if v != view]]:
            paired = compared[[view, other]].dropna()
            correlations.append(dict(view=view, other=other, n=len(paired),
                                     correlation=paired[view].corr(paired[other])))
    return per_name.reset_index(), pd.DataFrame(correlations)


def forecast(out: Path):
    """Read pinned research files and materialize forecasts plus auditable training evidence."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    protocol = json.loads((HERE / 'protocol.json').read_text())
    split = pd.Timestamp(protocol['historical_evaluation_after'])
    inputs = FROZEN / 'inputs'
    eligible, valuation = [pd.read_csv(inputs/name, index_col='date', parse_dates=True)
                           for name in ('prices_eligible.csv','prices_valuation.csv')]
    check_ledger(eligible, pd.read_csv(inputs/'availability_ledger.csv', parse_dates=['session_date']))
    history = pd.read_csv(inputs/'selection_history.csv', parse_dates=['selection_date','history_end'])
    calendar = pd.read_csv(FROZEN/'rebalance_calendar.csv',
                           parse_dates=['decision_date','assumed_execution_date','selection_state_id'])
    alignment, members, features, targets = build_panel(eligible, valuation, history, split)
    rows, seed_predictions, fits = walk_forward(alignment, members, features, targets, calendar, protocol['training'])
    equity, dependency = equity_error_diagnostics(rows, seed_predictions, valuation, split)
    for name, frame in [('forecasts',rows), ('forecast_alignment',alignment.rename_axis('date').reset_index()),
                        ('forecast_members',seed_predictions), ('forecast_fit_lineage',fits),
                        ('forecast_equity_errors',equity), ('forecast_error_dependency',dependency)]:
        frame.to_csv(out/(name+'.csv'), index=False)
    return rows
