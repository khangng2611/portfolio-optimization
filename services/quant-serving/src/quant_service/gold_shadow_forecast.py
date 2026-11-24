"""Derived five-session GOLD minus K5 view for the offline proposal observer."""

import csv
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import xgboost as xgb

from portfolio_contracts import canonical_hash
from portfolio_contracts.assets import EQUITY_IDS
from .gold_shadow_quotes import WARMUP_VERIFIED_AT, load_capture
from .selection_catalog import SelectionCatalog
from .selection_panel import load_panel
from .full import TZ
from .selection_ready import fit_index
from .snapshot_inputs import timestamp

RUN = "20261124T090146690849Z"
WARMUP_READY = timestamp(WARMUP_VERIFIED_AT)
SPLIT = date(2023, 9, 29)
DIGESTS = {
    "inputs/prices_eligible.csv": "c7b4c9a6a52a203afe53f8a88b46aa3f34e0d5f2d8f9512530b76821884e9c52",
    "inputs/prices_valuation.csv": "26d25e49fd41afd331fa4a975170cc76e600cdfa822914c489b581b6f4225f1c",
    "forecasts.csv": "15a1e71950d4bde209e1c21009ce1e6f4ccfd505c6cd5378dc77a1daa64ed62d",
}
SEEDS = (17, 41)
ROUNDS = 40
PARAMS = dict(max_depth=2, learning_rate=.05, subsample=.85, nthread=1, objective="reg:squarederror")
FEATURES = ("momentum_5", "momentum_20", "volatility_20")


def _warmup():
    configured = os.environ.get("GOLD_SHADOW_FORECAST_WARMUP")
    directory = (Path(configured) if configured else
                 Path(__file__).resolve().parents[4] / "phase2_gold_k5" / "revision" / "runs" / RUN)
    tables = []
    for name, digest in DIGESTS.items():
        content = (directory / name).read_bytes()
        if sha256(content).hexdigest() != digest:
            raise ValueError(f"GOLD_SHADOW_WARMUP_HASH_MISMATCH {name}")
        tables.append(list(csv.DictReader(StringIO(content.decode()))))
    return tables


def _seconds(day, hour=18):
    return datetime.combine(day, time(hour), TZ).timestamp()


def _iso(seconds):
    return datetime.fromtimestamp(float(seconds), timezone.utc).isoformat()


def _features(prices):
    windows = np.lib.stride_tricks.sliding_window_view(prices, 21)
    return np.column_stack((windows[:, -1] / windows[:, -6] - 1,
                            windows[:, -1] / windows[:, 0] - 1,
                            np.std(windows[:, 1:] / windows[:, :-1] - 1, axis=1, ddof=1)))


def _live_arrays(panel, dates, asset, quotes):
    """Return feature marks, economic marks and their actual receipt + policy cutoffs."""
    if asset != "GOLD":
        col = panel.ids.index(asset)
        valid = panel.valid[:len(dates), col]
        prices = np.where(valid, panel.prices[:len(dates), col], np.nan)
        known = np.maximum(panel.known_seconds[:len(dates), col], panel.policy_seconds[:len(dates), col])
        return prices, prices, known, known
    available, marks = {}, {}
    for key, row in quotes.items():
        day = date.fromisoformat(key)
        if day > dates[-1]:
            continue
        ask, bid = float(row["ask"]), float(row["bid"])
        if not (np.isfinite(ask) and 0 < bid <= ask):
            raise ValueError(f"Invalid SJC bid/ask at {key}")
        marks[day] = ask
        available[day] = max(_seconds(day + timedelta(days=1), 0), timestamp(row["received_at"]).timestamp())
    # The frozen contract uses the previous calendar day's ask even on a Monday.
    eligible_days = [d - timedelta(days=1) for d in dates]
    def take(mapping, days, missing):
        return np.array([mapping.get(day, missing) for day in days])
    return (take(marks, eligible_days, np.nan), take(marks, dates, np.nan),
            take(available, eligible_days, np.inf), take(available, dates, np.inf))


def _calibration(history, cutoff):
    ready = [r for r in history if r[3] <= cutoff]
    audit = dict(n=len(ready), historical_n=sum(r[4] == "historical" for r in ready),
                 prospective_n=sum(r[4] == "prospective" for r in ready),
                 last_origin=max((str(r[0]) for r in ready), default=None),
                 last_label_available_at=_iso(max(r[3] for r in ready)) if ready else None,
                 mse_daily=None, variance_daily=None)
    if not ready:
        return audit, None
    pred, actual = np.array([(r[1], r[2]) for r in ready]).T / 5
    mse, variance = float(np.mean((actual - pred)**2)), float(np.var(actual))
    audit.update(mse_daily=mse, variance_daily=variance)
    conf = float(np.clip(variance / (variance + mse), .1, .9)) if len(ready) >= 20 and variance + mse > 0 else None
    return audit, conf


def _names(selected):
    if len(selected) != 5 or len(set(selected)) != 5 or not set(selected) <= set(EQUITY_IDS):
        raise ValueError("Derived view requires exactly five distinct supported equities")
    return ["GOLD", *selected]


def _epoch_source(epoch, fit_cut):
    """Pin the latest selection publication available at this epoch, across all users."""
    cache = Path(os.environ["GOLD_SHADOW_FORECAST_EPOCHS"])
    bundles = Path(os.environ["BUNDLE_DIRECTORY"])
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{epoch}.json"
    if not path.exists():
        candidates = [(timestamp(v["decision_at"]), ready.bundle_hash, v)
                      for v, ready in SelectionCatalog(bundles)._entries()
                      if timestamp(v["decision_at"]).timestamp() <= fit_cut < timestamp(v["valid_until"]).timestamp()
                      and 0 <= (epoch-date.fromisoformat(v["as_of_date"])).days <= 7]
        source = None
        if candidates:
            published, digest, entry = max(candidates, key=lambda c: c[:2])
            source = dict(bundle_sha256=digest, published_at=published.isoformat(), panel=entry["panel"],
                          as_of_date=entry["as_of_date"], valid_until=entry["valid_until"],
                          panel_hash=entry["provenance"]["panel_hash"])
        record = dict(epoch=str(epoch), cutoff_at=_iso(fit_cut), source=source)
        with NamedTemporaryFile(dir=cache, delete=False) as stream:
            tmp = Path(stream.name)
            try:
                stream.write(json.dumps(record | {"sha256": canonical_hash(record)}).encode())
                stream.flush()
                os.fsync(stream.fileno())
                try:
                    os.link(tmp, path)
                except FileExistsError:
                    pass
            finally:
                tmp.unlink(missing_ok=True)
    pin = json.loads(path.read_bytes())
    digest = pin.pop("sha256")
    if canonical_hash(pin) != digest or (pin["epoch"], pin["cutoff_at"]) != (str(epoch), _iso(fit_cut)):
        raise ValueError("GOLD_SHADOW_EPOCH_PIN_MISMATCH")
    if not pin["source"]:
        return None, {}, pin
    source = pin["source"]
    panel = load_panel(bundles, source["panel"]["file"], source["panel"]["sha256"])
    if (panel.panel_hash != source["panel_hash"] or timestamp(panel.snapshot["created_at"]).timestamp() > fit_cut
            or not timestamp(source["published_at"]).timestamp() <= fit_cut < timestamp(source["valid_until"]).timestamp()
            or not 0 <= (epoch-date.fromisoformat(source["as_of_date"])).days <= 7):
        raise ValueError("GOLD_SHADOW_EPOCH_PANEL_MISMATCH")
    day = min(epoch, panel.dates[-1])
    capture = load_capture(panel, day, pin["cutoff_at"], os.environ["GOLD_SHADOW_DATASETS"],
                           os.environ["GOLD_SHADOW_ARCHIVE"])
    return panel, capture["gold_quotes"], pin


def forecast(panel, decision_session, selected, *, capture=None):
    """Fit, predict and audit only from the pinned snapshot, warmup and archived receipts."""
    if not capture or not capture.get("gold_quotes"):
        raise ValueError("GOLD_SHADOW_DATED_SJC_CAPTURE_REQUIRED")
    cutoff = timestamp(capture["cutoff_at"])
    decision = date.fromisoformat(str(decision_session))
    t = panel.dates.index(decision)
    if (cutoff < WARMUP_READY or panel.index_at(cutoff) != t
            or timestamp(panel.snapshot["created_at"]) > cutoff):
        raise ValueError("GOLD_SHADOW_DECISION_CUTOFF_MISMATCH")
    assets = _names(selected)
    dates = panel.dates[:t+1]
    eligible, valuation, forecasts = _warmup()
    warm_dates = [date.fromisoformat(row["date"]) for row in eligible]
    if dates[:len(warm_dates)] != warm_dates or decision <= warm_dates[-1]:
        raise ValueError("GOLD_SHADOW_WARMUP_CALENDAR_MISMATCH")
    epoch = fit_index(t)
    bootstrap = _seconds(dates[epoch]) < WARMUP_READY.timestamp()
    fit = fit_index(len(warm_dates) - 1) if bootstrap else epoch
    fit_cut = _seconds(dates[fit])
    # Bootstrap reconstructs the last historical epoch after the revised run was locked.
    frozen_origins = np.array([i for i in range(20, len(warm_dates) - 6)
                               if _seconds(warm_dates[i+6] + timedelta(days=1), 0) <= fit_cut
                               and not warm_dates[i] <= SPLIT < warm_dates[i+6]], dtype=int)
    day_known = np.array([_seconds(d + timedelta(days=1), 0) for d in dates])
    train_panel, train_quotes, epoch_pin = (None, {}, None) if bootstrap else _epoch_source(dates[epoch], fit_cut)
    train_dates = train_panel.dates[:fit+1] if train_panel else []
    if train_dates != dates[:len(train_dates)]:
        raise ValueError("GOLD_SHADOW_EPOCH_CALENDAR_MISMATCH")
    origins = np.arange(len(warm_dates), max(len(warm_dates), len(train_dates) - 6), dtype=int)
    fit_audit = dict(epoch=str(dates[epoch]), fit_date=str(dates[fit]), bootstrap=bootstrap,
                     model_age_sessions=t-fit, cutoff_at=_iso(fit_cut), warmup_run=RUN,
                     warmup_ready_at=WARMUP_READY.isoformat(), warmup_sha256=DIGESTS,
                     seeds=list(SEEDS), rounds=ROUNDS, parameters=PARAMS, xgboost=xgb.__version__,
                     features=list(FEATURES), panel_hash=panel.panel_hash, epoch_pin=epoch_pin,
                     historical_publication_verified=False)
    result = dict(status="fit_warmup", decision_session=str(decision), cutoff_at=cutoff.isoformat(),
                  selected_equity_ids=list(selected), prediction_5d=None, q_daily=None, confidence=None,
                  fit=fit_audit, components={}, calibration=None,
                  label=dict(start_session_offset=1, end_session_offset=6, gold_mark="SJC HCM ask VND/tael",
                             minimum_gold_availability="D+1 00:00 Asia/Ho_Chi_Minh"))
    cache = {}
    def live(asset):
        if asset not in cache:
            cache[asset] = _live_arrays(panel, dates, asset, capture["gold_quotes"])
        return cache[asset]

    fit_audit.update(historical_rows=len(frozen_origins), live_candidate_rows=len(origins))
    if not bootstrap and train_panel is None:
        result["reason"] = "NO_VALID_PUBLICATION_AT_MODEL_EPOCH"
        return result
    if len(frozen_origins) < 100:
        result["reason"] = "FEWER_THAN_100_MATURE_TRAINING_ROWS"
        return result
    for asset in assets:
        prices, _, known, _ = live(asset)
        current = _features(prices[t-20:t+1])
        if max(known[t-20:t+1]) > cutoff.timestamp() or not np.isfinite(current).all():
            raise ValueError(f"GOLD_SHADOW_FEATURE_UNAVAILABLE {asset} {decision}")
        live_origins = np.empty(0, dtype=int)
        live_X, live_y = np.empty((0, 3)), np.empty(0)
        max_known = WARMUP_READY.timestamp()
        if len(origins):
            fit_prices, marks, feature_known, mark_known = _live_arrays(train_panel, train_dates, asset, train_quotes)
            window_known = np.lib.stride_tricks.sliding_window_view(np.where(np.isfinite(fit_prices), feature_known, np.inf), 21)
            label_known = np.where(np.isfinite(marks), mark_known, np.inf)
            # All six independent models share the conservative GOLD D+1 label policy.
            receipt = np.maximum.reduce((day_known[origins+6], window_known[origins-20].max(axis=1),
                                         label_known[origins+1], label_known[origins+6]))
            live_origins = origins[receipt <= fit_cut]
            if len(live_origins):
                max_known = max(max_known, receipt[receipt <= fit_cut].max())
                live_X = _features(fit_prices)[live_origins-20]
                live_y = marks[live_origins+6] / marks[live_origins+1] - 1
        if not bootstrap and not len(live_origins):
            result.update(reason="NO_MATURE_POST_WARMUP_TRAINING_ROWS", unavailable_asset=asset, components={})
            return result
        all_origins = np.concatenate((frozen_origins, live_origins))
        last = all_origins[-1]
        initial = np.array([float(r[asset]) for r in eligible])
        economic = np.array([float(r[asset]) for r in valuation])
        X = np.vstack((_features(initial)[frozen_origins-20], live_X))
        y = np.concatenate((economic[frozen_origins+6] / economic[frozen_origins+1] - 1, live_y))
        if not all(np.isfinite(values).all() for values in (X, y, current)):
            raise ValueError(f"Non-finite derived-view inputs for {asset}")
        matrix = xgb.QuantileDMatrix(X, label=y, nthread=1)
        predictions = []
        for seed in SEEDS:
            model = xgb.train(PARAMS | {"seed": seed}, matrix, num_boost_round=ROUNDS)
            predictions.append(float(model.inplace_predict(current)[0]))
        result["components"][asset] = dict(
            features=dict(zip(FEATURES, current[0].tolist())), feature_start=str(dates[t-20]),
            feature_end=str(decision), feature_max_available_at=_iso(max(known[t-20:t+1])),
            label_start_offset=1, label_end_offset=6, seed_predictions=predictions,
            training_rows=len(all_origins), live_training_rows=len(live_origins),
            days_since_last_training_label=(decision-dates[last+6]).days,
            training_first_origin=str(dates[all_origins[0]]), training_last_origin=str(dates[last]),
            training_last_label_start=str(dates[last+1]), training_last_label_end=str(dates[last+6]),
            training_last_policy_available_at=_iso(day_known[last+6]), training_max_known_at=_iso(max_known),
            origins_sha256=sha256("\n".join(str(dates[i]) for i in all_origins).encode()).hexdigest(),
            prediction_5d=float(np.mean(predictions)),
            training_sha256=sha256(np.column_stack((X, y)).astype("<f8").tobytes()).hexdigest())
    members = result["components"]
    raw = members["GOLD"]["prediction_5d"] - float(np.mean([members[a]["prediction_5d"] for a in selected]))
    hist = [(r["date"], float(r["prediction"]), float(r["actual"]), timestamp(r["label_available_at"]).timestamp(), "historical")
            for r in forecasts if r["view"] == "derived" and r["prediction"] and r["actual"] and r["crosses_split"] == "False"]
    seen = set()
    mature_app_errors = []
    for prior in capture.get("prior_forecasts", []):
        origin = date.fromisoformat(prior["decision_session"])
        i = dates.index(origin)
        if origin in seen or origin <= warm_dates[-1] or i >= t:
            raise ValueError("Invalid or duplicate prior shadow origin")
        seen.add(origin)
        if i + 6 > t:
            continue
        issue = timestamp(prior["issued_at"]).timestamp()
        if not max(_seconds(origin), WARMUP_READY.timestamp()) <= issue < _seconds(dates[i+1], 9):
            raise ValueError("Prior shadow prediction issued outside decision window")
        actual, available = [], day_known[i+6]
        prior_assets = _names(prior["selected_equity_ids"])
        for asset in prior_assets:
            _, marks, _, known = live(asset)
            actual.append(marks[i+6] / marks[i+1] - 1)
            available = max(available, known[i+6], known[i+1])
        if not np.isfinite(actual).all() or available > cutoff.timestamp():
            continue
        prediction = float(prior["prediction_5d"])
        if not np.isfinite(prediction):
            raise ValueError("Non-finite prior shadow prediction")
        spread = actual[0] - float(np.mean(actual[1:]))
        hist.append((str(origin), prediction, spread, available, "prospective"))
        mature_app_errors.append(dict(origin=str(origin), issued_at=prior["issued_at"], label_start=str(dates[i+1]),
                                      label_end=str(dates[i+6]), label_available_at=_iso(available),
                                      realized_5d_by_asset=dict(zip(prior_assets, map(float, actual))),
                                      realized_spread_5d=spread, prediction_5d=prediction))
    audit, conf = _calibration(hist, cutoff.timestamp())
    audit.update(historical_run=RUN, prospective_errors=mature_app_errors)
    result.update(status="calibration_warmup" if conf is None else "active", prediction_5d=raw,
                  q_daily=raw/5 if conf is not None else None, confidence=conf, calibration=audit)
    return result
