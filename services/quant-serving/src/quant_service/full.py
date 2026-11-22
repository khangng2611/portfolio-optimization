"""Versioned mixed-asset panel and native Phase 1 full-universe inference."""

from bisect import bisect_right
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import xgboost as xgb

from portfolio_contracts import ModelUnavailable, canonical_hash, utcnow
from portfolio_core.phase1_full import (
    ASSET_IDS,
    EQUITY_IDS,
    schedule,
    select_equities,
    regime,
    adjust_views,
    validate_active_assets,
)
from . import phase1
from .snapshot_inputs import timestamp

UNIVERSE = "VN_PHASE1_FULL"
FEATURE_SCHEMA = "phase1-full-features-v1"
GOLD_PROVIDER = "giavang-sjc-hcm-archive-v1"
VFF_PROVIDER = "fmarket-vff-21-v1"
START = date(2020, 1, 14)
TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class FullModelPending(ModelUnavailable):
    code = "MODEL_REVIEW_PENDING"


class FullSelectionMismatch(ValueError):
    code = "SELECTION_MISMATCH"


class FullDataUnavailable(ValueError):
    def __init__(self, code, asset, observation_date, age_days):
        self.code = code
        self.details = dict(
            asset_id=asset,
            observation_date=str(observation_date),
            age_days=age_days,
            max_age_days=7,
        )
        super().__init__(
            f"{code}: {asset} eligible observation {observation_date} is {age_days} days old; freshness maximum is 7 days"
        )


def check_full_availability(state, now=None):
    """Shared publisher/worker gate; age is recomputed at actual use time."""
    now = now or utcnow()
    if state["freshness_max_age_days"] != 7:
        raise ValueError("Full freshness must remain 7 days")
    for asset in ["VFF", "GOLD", *EQUITY_IDS]:
        item = state["availability"][asset]
        observation = date.fromisoformat(item["observation_date"])
        age = (now.astimezone(TZ).date() - observation).days
        if (
            age < 0
            or timestamp(item["policy_available_at"]) > now
            or timestamp(item["available_at"]) > now
        ):
            raise ValueError("Full observation not yet available")
        if age > 7:
            code = (
                "VFF_STALE"
                if asset == "VFF"
                else "GOLD_STALE"
                if asset == "GOLD"
                else "INPUT_EXPIRED"
            )
            raise FullDataUnavailable(code, asset, observation, age)


class MixedPanel:
    def __init__(self, snapshot, observations, *, expected_hash, now=None, **policy):
        self.now = now or utcnow()
        if self.now.tzinfo is None or policy.get("max_age_days", 7) != 7:
            raise ValueError("Full Phase 1 requires aware time and freshness 7 days")
        manifest = {
            k: v
            for k, v in snapshot.items()
            if k not in {"id", "content_hash", "created_at"}
        }
        if (
            snapshot.get("content_hash") != expected_hash
            or canonical_hash(manifest) != expected_hash
        ):
            raise ValueError("Full snapshot manifest hash mismatch")
        if (
            snapshot.get("schema_version") != 2
            or snapshot.get("status") != "READY"
            or snapshot.get("quality_status") != "PASS"
            or snapshot.get("currency") != "VND"
            or snapshot.get("availability_policy") != "phase1-full-v1"
            or snapshot.get("data_origin") != "real"
            or snapshot.get("asset_ids") != list(ASSET_IDS)
            or snapshot.get("candidate_equity_ids") != list(EQUITY_IDS)
        ):
            raise ValueError("Unsupported full snapshot identity or quality")
        if (
            len(observations) != snapshot["observation_count"]
            or [r["revision_id"] for r in observations] != snapshot["revision_ids"]
            or len(set(snapshot["revision_ids"])) != len(observations)
            or canonical_hash({"observations": observations})
            != snapshot["observation_hash"]
        ):
            raise ValueError("Full snapshot observations hash mismatch")
        created = timestamp(snapshot["created_at"])
        if created > self.now:
            raise ValueError("Full snapshot unavailable at decision")
        calendar = [date.fromisoformat(d) for d in snapshot["calendar_sessions"]]
        if (
            calendar != sorted(set(calendar))
            or not calendar
            or calendar[-1] > self.now.astimezone(TZ).date()
        ):
            raise ValueError("Invalid full observed calendar")
        declared_gaps = snapshot.get("equity_missing_sessions", {})
        if not isinstance(declared_gaps, dict) or not set(declared_gaps) <= set(
            EQUITY_IDS
        ):
            raise ValueError("Invalid equity carry declaration")
        for asset, gaps in declared_gaps.items():
            if (
                not isinstance(gaps, list)
                or gaps != sorted(set(gaps))
                or not set(gaps) <= set(snapshot["calendar_sessions"])
            ):
                raise ValueError("Invalid equity carry dates")
        by_asset = {asset: [] for asset in ASSET_IDS}
        seen = set()
        known = []
        for row in observations:
            asset = row["asset_id"]
            day = date.fromisoformat(row["observation_date"])
            if asset not in by_asset or (asset, day) in seen:
                raise ValueError("Unexpected or duplicate full observation")
            seen.add((asset, day))
            ingested, available = (
                timestamp(row["ingested_at"]),
                timestamp(row["available_at"]),
            )
            if (
                not ingested <= available <= created
                or available.date() < day
                or row.get("data_origin") != "real"
            ):
                raise ValueError("Invalid full source availability")
            known.append(available)
            price = float(row["price_vnd"])
            if not np.isfinite(price) or price <= 0:
                raise ValueError("Invalid full source price")
            if asset in EQUITY_IDS:
                if (
                    row["provider"],
                    row["price_type"],
                    row["unit"],
                    row["price_basis"],
                ) != phase1.PRICE_CONVENTION:
                    raise ValueError("Invalid equity convention")
                eligible = datetime.combine(day, time(18), tzinfo=TZ)
            elif asset == "GOLD":
                if (
                    row["provider"] != GOLD_PROVIDER
                    or row["unit"] != "VND/tael"
                    or row["price_type"] != "close"
                    or row["price_basis"] != "raw_close"
                ):
                    raise ValueError("Invalid GOLD convention")
                eligible = datetime.combine(day + timedelta(days=1), time(), tzinfo=TZ)
            else:
                if (
                    row["provider"] != VFF_PROVIDER
                    or row["unit"] != "VND/unit"
                    or row["price_type"] != "nav"
                    or row["price_basis"] != "nav"
                ):
                    raise ValueError("Invalid VFF convention")
                metadata = row.get("source_metadata", {})
                if metadata.get("product_id") != 21:
                    raise ValueError("Invalid VFF identity")
                index = bisect_right(calendar, day) + 4
                if index >= len(calendar):
                    continue
                eligible = datetime.combine(calendar[index], time(18), tzinfo=TZ)
                record_time = metadata.get(
                    "provider_record_created_at"
                ) or metadata.get("raw_fund_record_created_at")
                if record_time:
                    eligible = max(eligible, timestamp(record_time))
            by_asset[asset].append((day, eligible, price, row))
        dates = [
            day
            for day in calendar
            if START <= day <= date.fromisoformat(snapshot["end_date"])
        ]
        if len(dates) < 146:
            raise ValueError("Insufficient full Phase 1 initialization history")
        self.ids = list(ASSET_IDS)
        self.dates = dates
        self.prices = np.empty((len(dates), 32))
        self.ledger = {}
        for j, asset in enumerate(ASSET_IDS):
            records = sorted(by_asset[asset], key=lambda r: (r[1], r[0]))
            cursor = 0
            latest = None
            ledger = []
            for i, day in enumerate(dates):
                decision = datetime.combine(day, time(18), tzinfo=TZ)
                while cursor < len(records) and records[cursor][1] <= decision:
                    candidate = records[cursor]
                    if latest is None or (candidate[0], candidate[1]) > (
                        latest[0],
                        latest[1],
                    ):
                        latest = candidate
                    cursor += 1
                if latest is None or (
                    asset in EQUITY_IDS
                    and latest[0] != day
                    and str(day) not in declared_gaps.get(asset, [])
                ):
                    raise ValueError(f"Missing eligible history for {asset} at {day}")
                self.prices[i, j] = latest[2]
                ledger.append(
                    dict(
                        observation_date=str(latest[0]),
                        policy_available_at=latest[1].isoformat(),
                        revision_id=latest[3]["revision_id"],
                        source_hash=latest[3].get(
                            "raw_source_hash", latest[3].get("source_hash")
                        ),
                        available_at=latest[3]["available_at"],
                        source_metadata=latest[3].get("source_metadata", {}),
                        carried=latest[0] != day,
                        carry_basis="frozen-forward-fill-declared-gap"
                        if asset in EQUITY_IDS and latest[0] != day
                        else "availability-asof",
                    )
                )
            self.ledger[asset] = ledger
        if self.dates[0] != START:
            raise ValueError("Full history initialization mismatch")
        self.returns = self.prices[1:] / self.prices[:-1] - 1
        self.snapshot = snapshot
        self.feature_known_at = max(known)
        self._state = None

    def selection_state(self):
        if self._state is not None:
            return self._state
        timing = schedule(len(self.dates))
        t, s, f = (
            timing["decision_index"],
            timing["selection_index"],
            timing["fit_index"],
        )
        if f is None:
            raise ModelUnavailable("Full model has insufficient fitting history")
        fs = timing["fit_selection_index"]

        def selection(index):
            prices = self.prices[:index, :30]
            selected = [EQUITY_IDS[j] for j in select_equities(prices)]
            pin = canonical_hash(
                dict(
                    candidate_equity_ids=list(EQUITY_IDS),
                    epoch=str(self.dates[index]),
                    prices_vnd=prices.tolist(),
                )
            )
            return selected, canonical_hash(
                {"input_hash": pin, "selected_equity_ids": selected}
            )

        selected, selection_id = selection(s)
        modelled, fit_selection_id = (
            (selected, selection_id) if fs == s else selection(fs)
        )
        self._state = timing | dict(
            selection_id=selection_id,
            selection_epoch=str(self.dates[s]),
            fit_epoch=str(self.dates[f]),
            model_selection_id=fit_selection_id,
            model_selection_epoch=str(self.dates[fs]),
            selected_equity_ids=selected,
            model_equity_ids=modelled,
            active_asset_ids=selected + ["GOLD", "VFF"],
            decision_date=str(self.dates[t]),
            training_cutoff=str(self.dates[f - 6]),
            training_equity_hash=canonical_hash(
                {
                    "dates": list(map(str, self.dates[: f - 5])),
                    "equity_ids": list(EQUITY_IDS),
                    "prices_vnd": self.prices[: f - 5, :30].tolist(),
                }
            ),
        )
        return self._state

    def availability(self):
        t = self.selection_state()["decision_index"]
        return {
            asset: self.ledger[asset][t]
            | {
                "age_days": (
                    self.now.astimezone(TZ).date()
                    - date.fromisoformat(self.ledger[asset][t]["observation_date"])
                ).days,
                "max_age_days": 7,
            }
            for asset in ASSET_IDS
        }

    def check_freshness(self):
        check_full_availability(
            {"availability": self.availability(), "freshness_max_age_days": 7}, self.now
        )

    def inputs(self):
        state = self.selection_state()
        t = state["decision_index"]
        returns = self.returns[t - 20 : t]
        active = state["active_asset_ids"]
        numerical = dict(
            asset_ids=self.ids,
            active_asset_ids=active,
            mean_returns=returns.mean(axis=0).tolist(),
            covariance=np.cov(returns, rowvar=False, ddof=1).tolist(),
            market_weights=[1 / 7 if asset in active else 0 for asset in self.ids],
        )
        rows = [
            phase1.feature_row(self.prices[:t, self.ids.index(asset)] / 1000)
            for asset in state["model_equity_ids"]
        ]
        full = state | dict(
            regime=regime(self.returns, t),
            availability=self.availability(),
            freshness_max_age_days=7,
        )
        features = dict(
            feature_schema_version=FEATURE_SCHEMA,
            feature_names=phase1.FEATURES,
            asset_ids=state["model_equity_ids"],
            feature_date=str(self.dates[t - 1]),
            feature_known_at=self.feature_known_at.isoformat(),
            rows=rows,
            daily_volatility={
                asset: float(
                    self.returns[t - 20 : t, self.ids.index(asset)].std(ddof=1)
                )
                for asset in state["model_equity_ids"]
            },
            state=full,
        )
        provenance = dict(
            snapshot_id=self.snapshot["id"],
            snapshot_hash=self.snapshot["content_hash"],
            observation_hash=self.snapshot["observation_hash"],
            data_origin="real",
            return_unit="daily_simple_fraction",
            availability_basis="ingestion-and-declared-historical-policy",
            historical_publication_verified=False,
            max_data_age_days=7,
            data_as_of=str(self.dates[t]),
            phase1_full=full,
        )
        return numerical, features, provenance


def infer_full(directory, value, manifest, reference):
    from .ml import phase1_predictions

    batch = value["ml_inference"]
    state = batch["state"]
    now = utcnow()
    if manifest.status != "APPROVED":
        raise FullModelPending("Full model is awaiting registry review")
    if manifest.fit_epoch.isoformat() != state["fit_epoch"]:
        raise FullModelPending("The scheduled full fit epoch needs an approved model")
    if (
        manifest.model_selection_id != state["model_selection_id"]
        or manifest.training_equity_hash != state["training_equity_hash"]
    ):
        raise FullSelectionMismatch(
            "Full model training/selection input pins differ from snapshot"
        )
    validate_active_assets(value["numerical"]["asset_ids"], state["active_asset_ids"])
    if state != value["provenance"]["phase1_full"]:
        raise ValueError("Full feature and provenance state differ")
    timing = schedule(state["decision_index"] + 1)
    if any(state[key] != number for key, number in timing.items()):
        raise ValueError("Full selection/fit schedule mismatch")
    if state["active_asset_ids"] != state["selected_equity_ids"] + ["GOLD", "VFF"]:
        raise ValueError("Full active selection mismatch")
    decision = timestamp(value["decision_at"])
    feature_date = date.fromisoformat(batch["feature_date"])
    as_of = date.fromisoformat(state["decision_date"])
    if (
        value["as_of_date"] != state["decision_date"]
        or not 1 <= (as_of - feature_date).days <= 14
        or as_of > decision.astimezone(TZ).date()
        or manifest.training_cutoff >= feature_date
        or timestamp(value["valid_until"]) <= now
    ):
        raise ValueError("Full snapshot/feature timing expired or mismatched")
    if (
        reference.sha256 != value["model_bundle_id"]
        or manifest.model_id is None
        or manifest.xgboost_version != xgb.__version__
        or value["universe_id"] != UNIVERSE
        or value["demo"]
        or value["numerical"]["asset_ids"] != list(ASSET_IDS)
        or value["numerical"]["active_asset_ids"] != state["active_asset_ids"]
        or manifest.asset_ids != state["model_equity_ids"]
        or manifest.full_asset_ids != list(ASSET_IDS)
        or manifest.fit_epoch.isoformat() != state["fit_epoch"]
        or manifest.model_selection_epoch.isoformat() != state["model_selection_epoch"]
        or manifest.model_selection_id != state["model_selection_id"]
        or manifest.training_equity_hash != state["training_equity_hash"]
        or manifest.training_cutoff.isoformat() != state["training_cutoff"]
        or batch["feature_names"] != phase1.FEATURES
        or batch["feature_schema_version"] != FEATURE_SCHEMA
        or batch["asset_ids"] != manifest.asset_ids
        or not timestamp(batch["feature_known_at"]) <= decision <= now
        or not manifest.trained_at <= manifest.approved_at <= decision
    ):
        raise ValueError(
            "Full model/selection/feature identity or availability mismatch"
        )
    checkpoint = datetime.combine(as_of, time(18), tzinfo=TZ)
    for item in state["availability"].values():
        if (
            date.fromisoformat(item["observation_date"]) > as_of
            or timestamp(item["policy_available_at"]) > checkpoint
        ):
            raise ValueError("Full source unavailable at quantitative checkpoint")
    if (
        value["provenance"]["data_origin"] != "real"
        or value["provenance"]["max_data_age_days"] != 7
    ):
        raise ValueError("Full source provenance or freshness mismatch")
    check_full_availability(state, now)
    rows = np.asarray(batch["rows"], dtype=float)
    if rows.shape != (5, 8) or not np.isfinite(rows).all():
        raise ValueError("Invalid full feature matrix")
    members = phase1_predictions(directory, manifest, rows)
    active = state["active_asset_ids"]
    p, q, confidence = [], [], []
    for asset, predictions in zip(manifest.asset_ids, members):
        if asset not in state["selected_equity_ids"]:
            continue
        mean, conf = phase1.ensemble_forecast(predictions)
        if abs(mean) < 0.001:
            continue
        daily_vol = batch["daily_volatility"][asset]
        if isinstance(daily_vol, bool) or not np.isfinite(daily_vol) or daily_vol < 0:
            raise ValueError("Invalid full daily volatility")
        vol = daily_vol * np.sqrt(5)
        annual = (
            0.5 * np.tanh(mean / vol)
            if vol > 1e-8
            else np.clip(mean * 252 / 5, -0.5, 0.5)
        )
        p.append([float(asset == a) for a in active])
        q.append(float(annual / 252))
        confidence.append(conf)
    views = adjust_views(
        dict(views_p=p, views_q=q, view_confidences=confidence) if p else None,
        state["regime"],
        active,
    )
    if not views.get("views_p"):
        raise ModelUnavailable("No valid full Phase 1 views")
    embedded = []
    for row in views["views_p"]:
        embedded.append(
            [row[active.index(a)] if a in active else 0.0 for a in ASSET_IDS]
        )
    views["views_p"] = embedded
    provenance = dict(
        model_id=manifest.model_id,
        model_manifest_hash=reference.sha256,
        selection_id=state["selection_id"],
        selection_epoch=state["selection_epoch"],
        fit_epoch=state["fit_epoch"],
        active_asset_ids=active,
        feature_date=batch["feature_date"],
        feature_batch_hash=canonical_hash(batch),
        confidence_policy="phase1-ensemble-disagreement-v1",
        view_policy="phase1-option-b-regime-v1",
        view_return_unit="daily_simple_fraction",
        horizon_sessions=5,
        training_cutoff=str(manifest.training_cutoff),
        trained_at=manifest.trained_at.isoformat(),
        approved_by=manifest.approved_by,
        booster_sha256={
            a: [b.sha256 for b in manifest.assets[a].boosters]
            for a in manifest.asset_ids
        },
    )
    return value["numerical"] | views, provenance
