"""Owner selection revisions and admission policy; no market calls while saving."""
import os
from datetime import date
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import object_session
from sqlalchemy.exc import IntegrityError

from portfolio_contracts import aware, canonical_hash
from portfolio_contracts.assets import canonical_candidates, candidate_hash
from .models import Portfolio, PortfolioAssetSelection


def enabled():
    return os.environ.get('USER_SELECTED_ASSETS_ENABLED', 'false').lower() == 'true'


def require_enabled():
    if not enabled():
        raise HTTPException(403, 'Lựa chọn tài sản chưa được bật.')


def revision_json(value):
    return {
        'revision_id': value.id, 'portfolio_id': value.portfolio_id,
        'portfolio_version': value.portfolio_version,
        'candidate_asset_ids': value.candidate_asset_ids, 'candidate_hash': value.candidate_hash,
        'selection_policy_id': value.selection_policy_id, 'risk_policy_id': value.risk_policy_id,
        'created_at': aware(value.created_at).isoformat(),
    }


def current_selection(portfolio):
    if portfolio.asset_selection_revision_id is None:
        return None
    value = object_session(portfolio).get(PortfolioAssetSelection, portfolio.asset_selection_revision_id)
    if value is None or value.portfolio_id != portfolio.id or value.owner_user_id != portfolio.owner_user_id:
        raise ValueError('Selection does not belong to this portfolio')
    return value


def create_selection_revision(session, portfolio, ids, key, expected_version, *, initial=False):
    ids = canonical_candidates(ids)
    body_hash = canonical_hash({'candidate_asset_ids': ids})
    if key is not None:
        existing = session.scalar(select(PortfolioAssetSelection).where(
            PortfolioAssetSelection.portfolio_id == portfolio.id,
            PortfolioAssetSelection.owner_user_id == portfolio.owner_user_id,
            PortfolioAssetSelection.idempotency_key == key,
        ))
        if existing:
            if existing.body_hash != body_hash or existing.portfolio_version != expected_version + 1:
                raise HTTPException(409, 'Idempotency-Key đã dùng cho lựa chọn hoặc phiên bản khác.')
            return existing
    if portfolio.version != expected_version:
        raise HTTPException(412, 'Danh mục đã thay đổi, hãy tải lại.')
    revision = PortfolioAssetSelection(
        id=str(uuid4()), portfolio_id=portfolio.id, owner_user_id=portfolio.owner_user_id,
        portfolio_version=expected_version if initial else expected_version + 1,
        candidate_asset_ids=ids, candidate_hash=candidate_hash(ids),
        actor=portfolio.owner_user_id, idempotency_key=key, body_hash=body_hash,
    )
    session.add(revision)
    try:
        session.flush()
    except IntegrityError:
        raise HTTPException(412, 'Danh mục đã thay đổi, hãy tải lại.') from None
    changed = session.execute(update(Portfolio).where(
        Portfolio.id == portfolio.id, Portfolio.version == expected_version,
    ).values(asset_selection_revision_id=revision.id, version=revision.portfolio_version)
      .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(412, 'Danh mục đã thay đổi, hãy tải lại.')
    session.refresh(portfolio)
    return revision


def stale_selection_details(readiness, reason):
    if reason not in {"VFF_STALE", "GOLD_STALE", "ASSET_DATA_STALE"}:
        return None
    for item in readiness.asset_status:
        asset = item.get("asset_id")
        if asset not in readiness.candidate_asset_ids or (
            reason != "ASSET_DATA_STALE" and asset != reason.removesuffix("_STALE")
        ):
            continue
        try:
            observation = date.fromisoformat(item["observation_date"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            str(observation) == item["observation_date"]
            and type(item.get("age_days")) is int and item["age_days"] > 7
            and type(item.get("max_age_days")) is int and item["max_age_days"] == 7
        ):
            return {key: item[key] for key in (
                "asset_id", "observation_date", "age_days", "max_age_days"
            )}
    return None
