"""One scheduled research decision using only the verified cutoff information panel."""

from datetime import datetime, timezone
from functools import lru_cache
import hashlib
from importlib import import_module
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
import xgboost as xgb

from portfolio_contracts.hybrid import FORWARD_POLICY, constraint_violations, hybrid_policy
from portfolio_core.hybrid import allocate_hybrid
from portfolio_core.phase1_full import ASSET_IDS, EQUITY_IDS, adjust_views, regime, select_equities


ROOT = Path(__file__).resolve().parents[1]
BASELINE = Path(os.environ.get('HYBRID_BASELINE_DIR', ROOT / 'outputs/step1/readiness_20261012/runs/availability-observed-contract-20261012T233110'))
BASELINE_HASH = '3f7457ae6c56ca6e02bcae5166cd7851e9a428d6e0b6859153c34937b55aedd6'
CONFIG_HASH = 'aaf0c8ae895f3ff5b2534219911a8f2f22659a469cf034f26ba4ebb1e41c7504'
RISK = {'conservative': 6., 'balanced': 3., 'growth': 1.5}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, expected):
    if path.is_symlink():
        raise ValueError(f'Invalid archive symlink: {path.name}')
    raw = path.read_bytes()
    if sha(raw) != expected:
        raise ValueError(f'Content hash mismatch: {path.name}')
    return raw


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False, indent=2) + '\n').encode()


@lru_cache(maxsize=1)
def frozen():
    source = (BASELINE / 'source_snapshot').resolve()
    baseline = json.loads(checked(BASELINE / 'manifest.json', BASELINE_HASH))
    config = json.loads(checked(BASELINE / 'run_config.json', CONFIG_HASH))
    sources = {r['path']: r['sha256'] for r in baseline['source']['files'] if r['path'].endswith('.py')}
    for path, expected in sources.items():
        checked(source / path, expected)
    # These absolute imports belong to the frozen tree; avoid importing the live
    # repository's identically named modules when running from a checkout.
    def frozen_name(name):
        return name.split('.')[0] in {'config', 'gen_view', 'utils'}
    previous = {k: v for k, v in sys.modules.items() if frozen_name(k)}
    for name in previous:
        del sys.modules[name]
    sys.path.insert(0, str(source))
    try:
        trainer = import_module('gen_view.xgboost.xgboost_core').XGBoostEnsembleModel
        views = import_module('gen_view.view_generators')
        for name, module in list(sys.modules.items()):
            if frozen_name(name) and str(Path(module.__file__).resolve().relative_to(source)) not in sources:
                raise ValueError(f'Unpinned module in frozen training source: {name}')
    finally:
        sys.path.remove(str(source))
        for name in list(sys.modules):
            if frozen_name(name):
                del sys.modules[name]
        sys.modules.update(previous)
    return trainer, views, config


def train_or_recover(workdir, training, day, offset, provenance, trainer):
    # Include input vintage, execution code and environment in the cache identity.
    raw_prices = training.to_csv(index_label='date', float_format='%.17g').encode()
    runtime = {pkg: version(pkg) for pkg in ('numpy', 'pandas', 'scikit-learn')}
    runtime['xgboost'] = xgb.__version__
    ident = {'fit_epoch': day, 'session_offset': offset, 'training_input_sha256': sha(raw_prices),
             'cutoff_provenance_sha256': sha(json_bytes(provenance)), 'config_sha256': CONFIG_HASH,
             'baseline_manifest_sha256': BASELINE_HASH, 'runner_sha256': sha(Path(__file__).read_bytes()), 'runtime': runtime}
    models = workdir / 'models'
    models.mkdir(parents=True, exist_ok=True)
    directory = models / sha(json_bytes(ident))
    if not directory.exists():
        with TemporaryDirectory(dir=models) as tmp:
            staged = Path(tmp) / 'model'
            staged.mkdir()
            start = datetime.now(timezone.utc).isoformat()
            estimator = trainer(model_params={'n_jobs': 1})
            estimator.train(training, verbose=False)
            equities = list(training.columns)
            if list(estimator.ensemble_models) != equities or len(estimator.feature_cols) != 8:
                raise ValueError('Incomplete frozen ensemble fit')
            details = {}
            for audit in estimator.training_audit:
                asset = audit['asset']
                train_end = audit['last_fitting_label_end']
                validation_start = audit['validation_start']
                valid_end = audit['validation_last_label_end']
                if not train_end < validation_start or valid_end != training.index[-1]:
                    raise ValueError('Invalid purged validation interval')
                members = []
                for member, booster in zip(audit['members'], estimator.ensemble_models[asset], strict=True):
                    file = f"{asset}-{member['seed']}.ubj"
                    native = bytes(booster.get_booster().save_raw(raw_format='ubj'))
                    (staged / file).write_bytes(native)
                    members.append({'file': file, 'sha256': sha(native), 'seed': member['seed'],
                                    'best_iteration': member['best_iteration'], 'validation_rmse': member['best_score']})
                if [m['seed'] for m in members] != list(range(42, 47)):
                    raise ValueError('Unexpected frozen seed order')
                details[asset] = {k: audit[k] for k in ('n_train', 'n_validation', 'purged_rows', 'scaler_mean', 'scaler_scale')}
                details[asset].update(train_label_end=str(train_end.date()), validation_start=str(validation_start.date()),
                                      validation_label_end=str(valid_end.date()), members=members)
            (staged / 'training-prices.csv').write_bytes(raw_prices)
            manifest = ident | {'asset_ids': equities, 'feature_names': estimator.feature_cols,
                                'training_cutoff': str(training.index[-1].date()), 'training_unit': 'thousand VND/share',
                                'started_at': start, 'trained_at': datetime.now(timezone.utc).isoformat(),
                                'feature_window': estimator.feature_window, 'prediction_horizon': estimator.prediction_horizon,
                                'by_asset': details}
            (staged / 'manifest.json').write_bytes(json_bytes(manifest))
            try:
                staged.rename(directory)
            except OSError:
                if not (directory / 'manifest.json').is_file():
                    raise
    path = directory / 'manifest.json'
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if any(manifest[k] != v for k, v in ident.items()):
        raise ValueError('Recovered model identity mismatch')
    return {'epoch': day, 'session_offset': offset, 'file': str(path.relative_to(workdir)), 'sha256': sha(raw)}


def model_manifest(workdir, reference, selected):
    base = (Path(workdir) / 'models').resolve()
    path = (Path(workdir).resolve() / reference['file'])
    if (path != path.resolve() or path.parent.parent != base or path.name != 'manifest.json'
            or len(path.parent.name) != 64 or any(c not in '0123456789abcdef' for c in path.parent.name)):
        raise ValueError('Invalid model manifest path')
    manifest = json.loads(checked(path, reference['sha256']))
    if (manifest['fit_epoch'] != reference['epoch'] or manifest['session_offset'] != reference['session_offset']
            or manifest['asset_ids'] != selected):
        raise ValueError('Model does not match the selected fit epoch')
    checked(path.parent / 'training-prices.csv', manifest['training_input_sha256'])
    return path, manifest


def native_members(directory, manifest, asset):
    for seed, member in zip(range(42, 47), manifest['by_asset'][asset]['members'], strict=True):
        if member['file'] != f'{asset}-{seed}.ubj' or member['seed'] != seed:
            raise ValueError('Invalid ensemble member order')
        yield member, checked(directory / member['file'], member['sha256'])


def verify_state(workdir, state):
    """Verify native artifacts in a committed receipt before scoring. Initial cash has no model."""
    if not state.get('model'):
        return
    selected = state['selection']['selected_equity_ids']
    if len(selected) != 5 or selected != [a for a in EQUITY_IDS if a in selected]:
        raise ValueError('Invalid archived K5 selection')
    path, manifest = model_manifest(workdir, state['model'], selected)
    for asset in selected:
        for _ in native_members(path.parent, manifest, asset):
            pass


def forecasts(workdir, reference, selected, prices, trainer):
    path, manifest = model_manifest(workdir, reference, selected)
    names = manifest['feature_names']
    estimator = trainer()
    predictions, evidence = {}, {}
    for asset in selected:
        row = estimator._compute_features(prices[asset]).iloc[-1][names].to_numpy()
        data = manifest['by_asset'][asset]
        matrix = xgb.DMatrix([(row - data['scaler_mean']) / data['scaler_scale']], feature_names=names, nthread=1)
        results = []
        for member, native in native_members(path.parent, manifest, asset):
            booster = xgb.Booster(params={'nthread': 1})
            booster.load_model(bytearray(native))
            if booster.feature_names != names or booster.attr('best_iteration') != str(member['best_iteration']):
                raise ValueError('Invalid native ensemble metadata')
            results.append(booster.predict(matrix, iteration_range=(0, member['best_iteration'] + 1))[0])
        values = np.array(results, dtype=np.float32)
        predictions[asset] = float(values.mean()), estimator._compute_ensemble_confidence(values)
        evidence[asset] = {'features': row.tolist(), 'members': values.tolist(),
                           'forecast': predictions[asset][0], 'confidence': predictions[asset][1]}
    return predictions, evidence


def decision(panel, cutoff_day: str, session_offset: int, workdir: Path, prior_state: dict):
    if type(session_offset) is not int or session_offset < 0 or session_offset % 5:
        raise ValueError('Not a scheduled decision')
    prices = panel['information']
    assets = list(ASSET_IDS)
    if list(prices.columns) != assets or panel['assets'] != assets or not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError('Unexpected full research asset order or index')
    if not prices.index.is_unique or not prices.index.is_monotonic_increasing or len(prices) < 145:
        raise ValueError('Invalid expanding information history')
    dates = [str(day.date()) for day in prices.index]
    if dates[-1] != cutoff_day or dates != panel['sessions'][-len(dates):]:
        raise ValueError('Information panel is not aligned to the decision session')
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError('Nonpositive or missing cutoff information')
    state = prior_state.copy()
    trainer, viewlib, config = frozen()
    equity = prices[list(EQUITY_IDS)] / 1000
    returns = prices.pct_change(fill_method=None).iloc[1:]
    market = regime(returns.to_numpy(), len(returns))
    record = dict(date=cutoff_day, regime=market['regime'], regime_evidence=market, state=state,
                  assets=assets, feature_end=dates[-2], covariance_end=cutoff_day)
    if session_offset % 20 == 0:
        prefix = equity.iloc[:-1]
        selected = [EQUITY_IDS[i] for i in select_equities(prefix.to_numpy())]
        state['selection'] = dict(epoch=cutoff_day, session_offset=session_offset, selected_equity_ids=selected,
                                  lookback_end=dates[-2], lookback_start=dates[0],
                                  input_hash=sha(prefix.to_csv(float_format='%.17g').encode()))
    selection = state.get('selection') or {}
    selection_offset = session_offset - session_offset % 20
    if selection.get('session_offset') != selection_offset or selection.get('epoch') != dates[-1 - (session_offset - selection_offset)]:
        return record | {'status': 'HOLD', 'reason': 'MISSING_SCHEDULED_SELECTION'}
    selected = selection['selected_equity_ids']
    active = selected + ['GOLD', 'VFF']
    if session_offset % 10 == 0:
        # t is the index of the decision close. Frozen ranking_absolute fits [:t-5].
        state['model'] = train_or_recover(workdir, equity[selected].iloc[:-6], cutoff_day,
                                         session_offset, panel['provenance'], trainer)
    ref = state.get('model') or {}
    fit_offset = session_offset - session_offset % 10
    if ref.get('session_offset') != fit_offset or ref.get('epoch') != dates[-1 - (session_offset - fit_offset)]:
        return record | {'status': 'HOLD', 'reason': 'MISSING_SCHEDULED_MODEL'}
    if panel.get('decision_block'):
        blocked = panel['decision_block']
        return record | {'status': 'HOLD', 'reason': blocked['reason'], 'details': blocked['details']}
    pred, evidence = forecasts(workdir, ref, selected, equity.iloc[:-1], trainer)
    recent = returns.tail(config['WINDOW'])
    ml = viewlib.generate_ml_views(pred, prediction_horizon=5, returns=recent)
    record.update(predictions=evidence, active_asset_ids=active)
    if not ml:
        return record | {'status': 'HOLD', 'reason': 'NO_VALID_ML_VIEWS'}
    p, q, confidence, names = viewlib.build_views_matrix(ml, active)
    views = adjust_views(dict(views_p=p, views_q=q, view_confidences=confidence), market, active)
    expanded = np.zeros((len(views['views_p']), len(assets)))
    expanded[:, [assets.index(asset) for asset in active]] = views['views_p']
    if len(expanded) > len(names):
        names.append('VFF_defensive_' + market['regime'])
    views['views_p'] = expanded.tolist()
    numerical = dict(asset_ids=assets, active_asset_ids=active, active_policy_version='user-selection-active-v1',
                     mean_returns=recent.mean().tolist(), covariance=recent.cov().to_numpy().tolist(),
                     market_weights=[1 / len(active) if a in active else 0. for a in assets],
                     tau=config['BL_TAU'], delta=config['BL_DELTA'], **views)
    weights, shares = {}, {}
    for profile, risk in RISK.items():
        constraints = dict(risk_aversion=max(risk, 5 if market['regime'] == 'crisis' else 1.5),
                           max_position_weight=.5, min_defensive_weight=.15, max_non_defensive_weight=.70,
                           defensive_asset_ids=['VFF'])
        pin = hybrid_policy(market['regime'], profile, version=FORWARD_POLICY)
        result = allocate_hybrid(numerical, constraints, pin)
        legs = result['diagnostics']['hybrid']
        mvo, bl = np.asarray(legs['mvo_weights']), np.asarray(legs['bl_ml_weights'])
        ratios = dict(candidate=pin['mvo_share'], regime_only=config['HYBRID_REGIME_RATIOS'][market['regime']],
                      v1=hybrid_policy(market['regime'], profile)['mvo_share'], bl_ml=0.)
        weights[profile] = {key: (alpha*mvo + (1-alpha)*bl).tolist() for key, alpha in ratios.items()}
        if any(constraint_violations(assets, w, constraints, tolerance=1e-8) for w in weights[profile].values()):
            raise ValueError('Research target violates its pinned constraints')
        shares[profile] = ratios
    return record | dict(status='TARGET', weights=weights, shares=shares, views=views, view_names=list(names))
