from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field, StringConstraints, model_validator, field_validator
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import object_session

from portfolio_contracts import (
    Constraints,
    DecisionContext,
    Envelope,
    OptimizeCommand,
    ModelUnavailable,
    ReadyInput,
    StrictModel,
    aware,
    canonical_hash,
    system_hybrid_enabled,
    system_hybrid_managed,
    utcnow,
)
from service_auth import AuthError
from service_observability import (
    capture_context,
    install_http_tracing,
    link_job,
    log_event,
    span,
    trace_fields,
)
from .models import (
    AcceptedTarget,
    Job,
    Outbox,
    Portfolio,
    Recommendation,
    RiskAssessment,
    PortfolioAssetSelection,
    User,
)
from .policy import RiskAnswers, effective_constraints, risk_policy, check_candidate_feasibility
from .selection import (enabled as selections_enabled, require_enabled, current_selection,
                        create_selection_revision, revision_json, stale_selection_details)
from portfolio_contracts.selection import CandidateSet, SelectionReadiness, SelectionContext, AssetCatalogItem
from portfolio_contracts.assets import canonical_candidates, supported_assets, CATALOG_VERSION
from .workflow import validate_result
from portfolio_contracts.explanation import RecommendationEvidence
from .runtime import StaleInput

HUMAN_ROLES = {
    "investor",
    "researcher",
    "data-operator",
    "model-reviewer",
    "system-admin",
}


class AssetSelectionInput(StrictModel):
    asset_ids: list[str] | None = Field(default=None, min_length=1, max_length=32)

    @field_validator("asset_ids")
    @classmethod
    def canonical(cls, value):
        return canonical_candidates(value) if value is not None else value

    @model_validator(mode="after")
    def exclusive(self):
        if self.asset_ids is not None and "universe_id" in self.model_fields_set:
            raise ValueError("asset_ids and universe_id are mutually exclusive")
        if getattr(self, "universe_id", None) == "USER_SELECTED":
            raise ValueError("Use asset_ids for a custom portfolio")
        return self


class NewPortfolio(AssetSelectionInput):
    name: str = Field(min_length=1, max_length=120, pattern=r"\S")
    capital_vnd: Decimal = Field(
        gt=0, le=Decimal("10000000000000000000"), max_digits=24, decimal_places=4
    )
    universe_id: str = Field(default="DEMO", pattern=r"^[A-Z0-9_-]{1,64}$")
    risk_aversion: float = Field(default=1.5, gt=0, le=100)
    max_position_weight: float = Field(default=0.5, gt=0, le=1)


class NewRecommendation(StrictModel):
    strategy: Literal["EW", "MVO", "BL_ML"] = "MVO"
    fallback_strategy: Literal["EW"] | None = None
    mode: Literal["system"] | None = None


class OnboardingPortfolio(AssetSelectionInput):
    name: str = Field(min_length=1, max_length=120, pattern=r"\S")
    capital_vnd: Decimal = Field(
        gt=0, le=Decimal("10000000000000000000"), max_digits=24, decimal_places=4
    )
    universe_id: str = Field(default="DEMO", pattern=r"^[A-Z0-9_-]{1,64}$")
    answers: RiskAnswers


class RiskAssessmentRequest(StrictModel):
    answers: RiskAnswers


class RiskPolicyState(StrictModel):
    risk_profile: dict | None
    constraints: Constraints
    policy_version_id: str


class RiskAssessmentPreview(StrictModel):
    portfolio_id: UUID
    portfolio_version: int
    before: RiskPolicyState
    after: RiskPolicyState


class RiskAssessmentRevision(StrictModel):
    id: UUID
    portfolio_id: UUID
    portfolio_version: int
    reason: Literal["onboarding", "reassessment"]
    created_at: datetime
    answers: RiskAnswers
    constraints: Constraints
    risk_profile: dict
    mapping_version: str
    policy_version_id: str


class RiskAssessmentHistoryEntry(RiskAssessmentRevision):
    is_active: bool


class PortfolioUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"\S")
    capital_vnd: Decimal | None = Field(
        default=None,
        gt=0,
        le=Decimal("10000000000000000000"),
        max_digits=24,
        decimal_places=4,
    )
    risk_aversion: float | None = Field(default=None, gt=0, le=100)
    max_position_weight: float | None = Field(default=None, gt=0, le=1)


class StrategyReadiness(StrictModel):
    strategy: Literal["EW", "MVO", "BL_ML"]
    available: bool
    reason_code: Literal[
        "READY",
        "MODEL_UNAVAILABLE",
        "MODEL_INVALID",
        "INPUT_EXPIRED",
        "INPUT_UNAVAILABLE",
        "INPUT_INVALID",
        "VFF_STALE", "GOLD_STALE", "MODEL_REVIEW_PENDING", "SELECTION_MISMATCH",
    ]


class InputReadiness(StrictModel):
    # Additive diagnostics only: immutable ReadyInput execution pins are unchanged.
    provenance: dict | None = None
    bundle_id: str | None = None
    bundle_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    snapshot_id: str | None = None
    approved_model_id: UUID | None = None
    model_manifest_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    universe_id: str = Field(pattern=r"^[A-Z0-9_-]{1,64}$")
    asset_ids: list[str]
    as_of_date: date | None
    valid_until: datetime | None
    demo: bool
    data_origin: Literal["real", "synthetic", "unverified"]
    status: Literal["READY", "EXPIRED", "UNAVAILABLE"]
    reason_code: Literal["READY", "INPUT_EXPIRED", "INPUT_UNAVAILABLE", "INPUT_INVALID", "VFF_STALE", "GOLD_STALE", "MODEL_REVIEW_PENDING", "SELECTION_MISMATCH"]
    strategies: list[StrategyReadiness]
    next_action: Literal["NONE", "REFRESH_DATA", "CONTACT_OPERATOR"]
    checked_at: datetime


def profile_policy_id(profile):
    if not profile:
        return "manual-constraints-v1"
    legacy = f"{profile.get('mapping_version', 'risk-policy-v1')}:{profile['profile']}"
    return f"{legacy}:{profile['version_id']}" if profile.get("version_id") else legacy


def policy_id(value):
    return profile_policy_id(value.risk_profile)


def assessment_json(value):
    return {
        "id": value.id,
        "portfolio_id": value.portfolio_id,
        "portfolio_version": value.portfolio_version,
        "reason": value.reason,
        "created_at": aware(value.created_at).isoformat(),
        "answers": value.answers,
        "constraints": value.constraints,
        "risk_profile": value.risk_profile,
        "mapping_version": value.mapping_version,
        "policy_version_id": value.policy_version_id,
    }


def assessment_revision(
    portfolio, profile, constraints, *, reason, key=None, body_hash=None
):
    revision_id = str(uuid4())
    profile = profile | {"version_id": revision_id}
    return RiskAssessment(
        id=revision_id,
        portfolio_id=portfolio.id,
        owner_user_id=portfolio.owner_user_id,
        portfolio_version=portfolio.version,
        reason=reason,
        answers=profile["answers"],
        constraints=constraints,
        risk_profile=profile,
        mapping_version=profile["mapping_version"],
        policy_version_id=profile_policy_id(profile),
        idempotency_key=key,
        body_hash=body_hash,
    )


def target_json(value):
    return {
        "id": value.id,
        "portfolio_id": value.portfolio_id,
        "recommendation_id": value.recommendation_id,
        "portfolio_version": value.portfolio_version,
        "accepted_at": aware(value.accepted_at).isoformat(),
        "allocation": value.allocation,
    }


def portfolio_json(value):
    result = {
        "id": value.id,
        "name": value.name,
        "capital_vnd": str(value.capital_vnd),
        "universe_id": value.universe_id,
        "constraints": value.constraints,
        "version": value.version,
        "policy_version_id": policy_id(value),
        "risk_profile": value.risk_profile,
    }
    selection = current_selection(value)
    if selection is not None:
        result["asset_selection"] = revision_json(selection)
    return result


def create_app(*, sessions, verifier, resolver, account_active=None):
    app = FastAPI(title="Portfolio Service", version="0.1.0")
    install_http_tracing(app)
    bearer = HTTPBearer(auto_error=False)

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    def error(request, status, code, message, headers=None, *, details=None):
        public_error = {"code": code, "message": message, "retryable": status == 503}
        if details is not None:
            public_error["details"] = details
        return JSONResponse(
            status_code=status,
            content={
                "error": public_error,
                "request_id": request.state.request_id,
            },
            headers=headers,
        )

    @app.exception_handler(StaleInput)
    async def stale_input_error(request: Request, exc: StaleInput):
        return JSONResponse(status_code=409, content={
            "error": exc.detail | {"retryable": False},
            "request_id": request.state.request_id,
        })

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if exc.status_code == 409 and isinstance(exc.detail, dict):
            return error(request, 409, exc.detail["code"], exc.detail["message"], exc.headers, details=exc.detail.get("details"))
        return error(
            request,
            exc.status_code,
            {
                401: "UNAUTHENTICATED",
                403: "FORBIDDEN",
                404: "NOT_FOUND",
                409: "CONFLICT",
                429: "QUOTA_EXCEEDED",
                503: "DEPENDENCY_UNAVAILABLE",
            }.get(exc.status_code, "INVALID_REQUEST"),
            str(exc.detail),
            exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc):
        return error(request, 422, "INVALID_INPUT", "Dữ liệu yêu cầu không hợp lệ.")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc):
        return error(
            request, 503, "DATABASE_UNAVAILABLE", "Dữ liệu tạm thời không khả dụng."
        )

    def principal(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ):
        if credentials is None:
            raise HTTPException(
                401, "Cần đăng nhập.", headers={"WWW-Authenticate": "Bearer"}
            )
        try:
            value = verifier.verify(credentials.credentials)
        except AuthError:
            raise HTTPException(
                401,
                "Phiên đăng nhập không hợp lệ.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None
        required = "portfolio:read" if request.method == "GET" else "portfolio:write"
        if not HUMAN_ROLES.intersection(value.roles) or required not in value.scopes:
            raise HTTPException(403, "Không có quyền thực hiện thao tác.")
        return value

    def owner(identity=Depends(principal)):
        with sessions.begin() as session:
            user = session.scalar(
                select(User).where(
                    User.issuer == identity.issuer, User.subject == identity.subject
                )
            )
            if user is None:
                try:
                    with session.begin_nested():
                        user = User(issuer=identity.issuer, subject=identity.subject)
                        session.add(user)
                        session.flush()
                except IntegrityError:
                    user = session.scalar(
                        select(User).where(
                            User.issuer == identity.issuer,
                            User.subject == identity.subject,
                        )
                    )
            return user.id

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        with sessions() as session:
            session.execute(text("SELECT 1 FROM app_user LIMIT 1"))
        return {"status": "ready"}

    @app.get("/api/v1/me")
    def me(identity=Depends(principal), user_id=Depends(owner)):
        return {"id": user_id, "roles": sorted(identity.roles & HUMAN_ROLES)}

    @app.get("/api/v1/universes")
    def universes(identity=Depends(principal)):
        try:
            return resolver.universes()
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(
                503, "Danh sách dữ liệu phục vụ chưa sẵn sàng."
            ) from None

    def resolve_readiness(universe_id=None):
        try:
            value = resolver.readiness(universe_id)
            if universe_id is not None:
                result = InputReadiness.model_validate(value)
                if result.universe_id != universe_id:
                    raise ValueError("Readiness universe mismatch")
                return result
            if not isinstance(value, list):
                raise ValueError("Invalid readiness catalog")
            return [InputReadiness.model_validate(item) for item in value]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise HTTPException(503, "Dữ liệu phục vụ chưa sẵn sàng.") from None

    @app.get("/api/v1/universes/readiness", response_model=list[InputReadiness])
    def universes_readiness(identity=Depends(principal)):
        return resolve_readiness()

    @app.get("/api/v1/assets/catalog")
    def asset_catalog(user_id=Depends(owner)):
        try:
            value = resolver.catalog()
            assets = [AssetCatalogItem.model_validate(item).model_dump(mode="json") for item in value["assets"]]
            if value["catalog_version"] != CATALOG_VERSION or [a["asset_id"] for a in assets] != [a["asset_id"] for a in supported_assets()]:
                raise ValueError("Catalog mismatch")
        except (httpx.HTTPError, ValueError, KeyError, AttributeError, TypeError):
            assets = [AssetCatalogItem.model_validate(item).model_dump(mode="json") for item in supported_assets()]
        return {"catalog_version": CATALOG_VERSION, "selection_enabled": selections_enabled(), "assets": assets}

    @app.post("/api/v1/portfolios", status_code=201)
    def create_portfolio(body: NewPortfolio, user_id=Depends(owner)):
        universe = "USER_SELECTED" if body.asset_ids is not None else body.universe_id
        if body.asset_ids is not None:
            require_enabled()
        with sessions.begin() as session:
            value = Portfolio(
                owner_user_id=user_id,
                name=body.name.strip(),
                capital_vnd=body.capital_vnd,
                universe_id=universe,
                constraints=effective_constraints(Constraints(
                    risk_aversion=body.risk_aversion,
                    max_position_weight=body.max_position_weight,
                ), universe).model_dump(),
            )
            session.add(value)
            session.flush()
            if body.asset_ids is not None:
                create_selection_revision(session, value, body.asset_ids, None, value.version, initial=True)
            return portfolio_json(value)

    @app.get("/api/v1/portfolios")
    def list_portfolios(
        response: Response,
        limit: int = Query(default=100, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=1_000_000),
        q: Annotated[
            str, StringConstraints(strip_whitespace=True, max_length=120)
        ] = "",
        risk_profile: Literal[
            "all", "manual", "conservative", "balanced", "growth"
        ] = "all",
        sort: Literal["created_desc", "name_asc", "capital_desc"] = "created_desc",
        user_id=Depends(owner),
    ):
        filters = [Portfolio.owner_user_id == user_id]
        if q.strip():
            filters.append(Portfolio.name.icontains(q.strip(), autoescape=True))
        if risk_profile == "manual":
            filters.append(Portfolio.risk_profile.is_(None))
        elif risk_profile != "all":
            filters.append(
                Portfolio.risk_profile["profile"].as_string() == risk_profile
            )
        order = {
            "created_desc": Portfolio.created_at.desc(),
            "name_asc": func.lower(Portfolio.name).asc(),
            "capital_desc": Portfolio.capital_vnd.desc(),
        }[sort]
        with sessions() as session:
            page_headers(
                response, session, select(Portfolio).where(*filters), limit, offset
            )
            return [
                portfolio_json(p)
                for p in session.scalars(
                    select(Portfolio)
                    .where(*filters)
                    .order_by(order, Portfolio.id.asc())
                    .limit(limit)
                    .offset(offset)
                )
            ]

    def page_headers(response, session, query, limit, offset):
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Limit"] = str(limit)
        response.headers["X-Offset"] = str(offset)

    @app.post("/api/v1/onboarding/portfolios", status_code=201)
    def onboarding(body: OnboardingPortfolio, user_id=Depends(owner)):
        universe = "USER_SELECTED" if body.asset_ids is not None else body.universe_id
        if body.asset_ids is not None:
            require_enabled()
        profile, constraints = risk_policy(body.answers, universe)
        with sessions.begin() as session:
            value = Portfolio(
                owner_user_id=user_id,
                name=body.name.strip(),
                capital_vnd=body.capital_vnd,
                universe_id=universe,
                constraints=constraints.model_dump(),
                risk_profile=profile,
            )
            session.add(value)
            session.flush()
            revision = assessment_revision(
                value, profile, constraints.model_dump(), reason="onboarding"
            )
            value.risk_profile = revision.risk_profile
            session.add(revision)
            session.flush()
            if body.asset_ids is not None:
                create_selection_revision(session, value, body.asset_ids, None, value.version, initial=True)
            return portfolio_json(value)

    def owned_portfolio(session, portfolio_id, user_id, *, lock=False):
        query = select(Portfolio).where(
            Portfolio.id == str(portfolio_id), Portfolio.owner_user_id == user_id
        )
        value = session.scalar(query.with_for_update() if lock else query)
        if value is None:
            raise HTTPException(404, "Không tìm thấy danh mục.")
        return value

    @app.get("/api/v1/portfolios/{portfolio_id}/asset-selections")
    def selection_history(portfolio_id: UUID, response: Response, user_id=Depends(owner)):
        with sessions() as session:
            value = owned_portfolio(session, portfolio_id, user_id)
            response.headers["ETag"] = f'"{value.version}"'
            return [revision_json(item) for item in session.scalars(
                select(PortfolioAssetSelection).where(
                    PortfolioAssetSelection.portfolio_id == value.id,
                    PortfolioAssetSelection.owner_user_id == user_id,
                ).order_by(PortfolioAssetSelection.portfolio_version.desc())
            )]

    @app.post("/api/v1/portfolios/{portfolio_id}/asset-selections", status_code=201)
    def edit_selection(portfolio_id: UUID, body: CandidateSet, response: Response,
                       user_id=Depends(owner), if_match: str | None = Header(default=None),
                       idempotency_key: str | None = Header(default=None)):
        with sessions.begin() as session:
            value = owned_portfolio(session, portfolio_id, user_id, lock=True)
            require_enabled()
            if current_selection(value) is None:
                raise HTTPException(409, "Danh mục cũ giữ nguyên bộ tài sản đã lưu.")
            if if_match is None:
                raise HTTPException(428, "Cần If-Match từ phiên bản danh mục hiện tại.")
            if not if_match.startswith('"') or not if_match.endswith('"') or not if_match[1:-1].isdigit():
                raise HTTPException(400, "If-Match không hợp lệ.")
            if not idempotency_key or not 1 <= len(idempotency_key) <= 128 or any(ord(c) < 33 or ord(c) > 126 for c in idempotency_key):
                raise HTTPException(400, "Cần Idempotency-Key hợp lệ.")
            try:
                revision = create_selection_revision(session, value, body.candidate_asset_ids,
                                                     idempotency_key, int(if_match[1:-1]))
            except ValueError:
                raise HTTPException(422, "Tài sản không hợp lệ.") from None
            response.headers["ETag"] = f'"{revision.portfolio_version}"'
            return revision_json(revision)

    @app.post(
        "/api/v1/portfolios/{portfolio_id}/risk-assessments/preview",
        response_model=RiskAssessmentPreview,
    )
    def preview_risk_assessment(
        portfolio_id: UUID,
        body: RiskAssessmentRequest,
        response: Response,
        user_id=Depends(owner),
    ):
        with sessions() as session:
            value = owned_portfolio(session, portfolio_id, user_id)
            profile, constraints = risk_policy(body.answers, value.universe_id)
            response.headers["ETag"] = f'"{value.version}"'
            return {
                "portfolio_id": value.id,
                "portfolio_version": value.version,
                "before": {
                    "risk_profile": value.risk_profile,
                    "constraints": value.constraints,
                    "policy_version_id": policy_id(value),
                },
                "after": {
                    "risk_profile": profile,
                    "constraints": constraints.model_dump(),
                    "policy_version_id": profile_policy_id(profile),
                },
            }

    @app.get(
        "/api/v1/portfolios/{portfolio_id}/risk-assessments",
        response_model=list[RiskAssessmentHistoryEntry],
    )
    def list_risk_assessments(
        portfolio_id: UUID,
        response: Response,
        limit: int = Query(default=100, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=1_000_000),
        user_id=Depends(owner),
    ):
        with sessions() as session:
            value = owned_portfolio(session, portfolio_id, user_id)
            query = select(RiskAssessment).where(
                RiskAssessment.portfolio_id == value.id,
                RiskAssessment.owner_user_id == user_id,
            )
            page_headers(response, session, query, limit, offset)
            response.headers["ETag"] = f'"{value.version}"'
            active_id = (value.risk_profile or {}).get("version_id")
            return [
                assessment_json(revision) | {"is_active": revision.id == active_id}
                for revision in session.scalars(
                    query.order_by(
                        RiskAssessment.portfolio_version.desc(), RiskAssessment.id.asc()
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ]

    @app.post(
        "/api/v1/portfolios/{portfolio_id}/risk-assessments",
        status_code=201,
        response_model=RiskAssessmentRevision,
    )
    def confirm_risk_assessment(
        portfolio_id: UUID,
        body: RiskAssessmentRequest,
        response: Response,
        user_id=Depends(owner),
        if_match: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ):
        body_hash = canonical_hash(body.model_dump())
        with sessions.begin() as session:
            value = owned_portfolio(session, portfolio_id, user_id, lock=True)
            profile, constraints = risk_policy(body.answers, value.universe_id)
            if if_match is None:
                raise HTTPException(428, "Cần If-Match từ phiên bản danh mục hiện tại.")
            if (
                not idempotency_key
                or not 1 <= len(idempotency_key) <= 128
                or any(ord(c) < 33 or ord(c) > 126 for c in idempotency_key)
            ):
                raise HTTPException(
                    400, "Cần Idempotency-Key hợp lệ (1–128 ký tự ASCII)."
                )
            existing = session.scalar(
                select(RiskAssessment).where(
                    RiskAssessment.portfolio_id == value.id,
                    RiskAssessment.owner_user_id == user_id,
                    RiskAssessment.idempotency_key == idempotency_key,
                )
            )
            if existing:
                if existing.body_hash != body_hash:
                    raise HTTPException(
                        409, "Idempotency-Key đã dùng cho nội dung khác."
                    )
                response.headers["ETag"] = f'"{existing.portfolio_version}"'
                return assessment_json(existing)
            if if_match != f'"{value.version}"':
                raise HTTPException(412, "Danh mục đã thay đổi, hãy tải lại.")
            # The row lock serializes confirmations on PostgreSQL; the version
            # predicate also protects engines without row-level FOR UPDATE.
            version = value.version
            revision = assessment_revision(
                value,
                profile,
                constraints.model_dump(),
                reason="reassessment",
                key=idempotency_key,
                body_hash=body_hash,
            )
            revision.portfolio_version = version + 1
            changed = session.execute(
                update(Portfolio)
                .where(Portfolio.id == value.id, Portfolio.version == version)
                .values(
                    version=version + 1,
                    constraints=revision.constraints,
                    risk_profile=revision.risk_profile,
                )
                .execution_options(synchronize_session=False)
            )
            if changed.rowcount != 1:
                raise HTTPException(412, "Danh mục đã thay đổi, hãy tải lại.")
            session.add(revision)
            session.flush()
            response.headers["ETag"] = f'"{revision.portfolio_version}"'
            return assessment_json(revision)

    def selected_readiness(value, revision):
        local = dict(portfolio_version=value.version, revision_id=revision.id,
                     candidate_hash=revision.candidate_hash, candidate_asset_ids=revision.candidate_asset_ids,
                     checked_at=utcnow())
        assessment = object_session(value).get(RiskAssessment, value.risk_profile["version_id"]) if value.risk_profile and value.risk_profile.get("version_id") else None
        reason = "INPUT_UNAVAILABLE" if not selections_enabled() else (
            "RISK_PROFILE_REQUIRED" if assessment is None or assessment.portfolio_id != value.id or assessment.owner_user_id != value.owner_user_id or value.risk_profile.get("mapping_version") != "custom-mixed-risk-v1"
            else check_candidate_feasibility(revision.candidate_asset_ids, value.constraints, "BL_ML")
        )
        if reason:
            return SelectionReadiness(**local, reason_code=reason, strategies=[
                {"strategy": strategy, "can_submit": False, "reason_code": reason} for strategy in ("EW", "MVO", "BL_ML")
            ])
        try:
            response = SelectionReadiness.model_validate(resolver.selection_ready({
                key: item for key, item in (local | {
                    "constraints": value.constraints,
                }).items() if key != "checked_at"
            }))
            if response.candidate_hash != revision.candidate_hash or response.candidate_asset_ids != revision.candidate_asset_ids:
                raise ValueError("Selection readiness mismatch")
            return response.model_copy(update={"portfolio_version": value.version, "revision_id": UUID(str(revision.id))})
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            return SelectionReadiness(**local, reason_code="INPUT_UNAVAILABLE")

    def hybrid_readiness(readiness):
        by_strategy = {item.strategy: item for item in readiness.strategies}
        blocked = next((by_strategy[s].reason_code for s in ("BL_ML", "MVO")
                        if s in by_strategy and not by_strategy[s].can_submit), None)
        ready = all(s in by_strategy and by_strategy[s].can_submit for s in ("BL_ML", "MVO"))
        reason = "READY" if ready else blocked or readiness.reason_code
        return SelectionReadiness.model_validate(readiness.model_dump() | {
            "can_submit": ready, "reason_code": reason,
            "strategies": [{"strategy": "HYBRID", "can_submit": ready, "reason_code": reason}],
        })

    @app.get(
        "/api/v1/portfolios/{portfolio_id}/readiness", response_model=InputReadiness | SelectionReadiness
    )
    def portfolio_readiness(portfolio_id: UUID, user_id=Depends(owner)):
        with sessions() as session:
            value = owned_portfolio(session, portfolio_id, user_id)
            revision = current_selection(value)
            if system_hybrid_managed() and not system_hybrid_enabled():
                return hybrid_readiness(SelectionReadiness(
                    candidate_asset_ids=revision.candidate_asset_ids if revision else [],
                    reason_code="INPUT_UNAVAILABLE", checked_at=utcnow(),
                ))
            if revision is not None:
                readiness = selected_readiness(value, revision)
                return hybrid_readiness(readiness) if system_hybrid_enabled() else readiness
            if system_hybrid_enabled():
                return hybrid_readiness(SelectionReadiness(reason_code="ASSET_SELECTION_REQUIRED", checked_at=utcnow()))
            universe_id = value.universe_id
        return resolve_readiness(universe_id)

    def target_query(portfolio_id, user_id):
        return select(AcceptedTarget).where(
            AcceptedTarget.portfolio_id == str(portfolio_id),
            AcceptedTarget.owner_user_id == user_id,
        )

    def targets(session, portfolio_id, user_id, *, limit=100, offset=0):
        return [
            target_json(value)
            for value in session.scalars(
                target_query(portfolio_id, user_id)
                .order_by(
                    AcceptedTarget.portfolio_version.desc(),
                    AcceptedTarget.accepted_at.desc(),
                    AcceptedTarget.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
        ]

    @app.get("/api/v1/portfolios/{portfolio_id}/targets")
    def list_targets(
        portfolio_id: UUID,
        response: Response,
        limit: int = Query(default=100, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=1_000_000),
        user_id=Depends(owner),
    ):
        with sessions() as session:
            owned_portfolio(session, portfolio_id, user_id)
            page_headers(
                response, session, target_query(portfolio_id, user_id), limit, offset
            )
            return targets(session, portfolio_id, user_id, limit=limit, offset=offset)

    @app.get("/api/v1/portfolios/{portfolio_id}/dashboard")
    def dashboard(portfolio_id: UUID, user_id=Depends(owner)):
        with sessions.begin() as session:
            value = owned_portfolio(session, portfolio_id, user_id, lock=True)
            history = targets(session, portfolio_id, user_id)
            return {
                "portfolio": portfolio_json(value),
                "accepted_target": history[0] if history else None,
                "target_matches_portfolio": bool(
                    history and history[0]["portfolio_version"] == value.version
                ),
                "proposal_count": session.scalar(
                    select(func.count())
                    .select_from(Recommendation)
                    .where(
                        Recommendation.portfolio_id == value.id,
                        Recommendation.owner_user_id == user_id,
                    )
                ),
                "holdings_status": "NOT_TRACKED",
            }

    @app.post("/api/v1/recommendations/{recommendation_id}/accept")
    def accept_target(
        recommendation_id: UUID,
        body: StrictModel,
        response: Response,
        user_id=Depends(owner),
        if_match: str | None = Header(default=None),
    ):
        with sessions.begin() as session:
            proposal = session.scalar(
                select(Recommendation).where(
                    Recommendation.id == str(recommendation_id),
                    Recommendation.owner_user_id == user_id,
                )
            )
            if proposal is None:
                raise HTTPException(404, "Không tìm thấy đề xuất.")
            value = owned_portfolio(session, proposal.portfolio_id, user_id, lock=True)
            if if_match is None:
                raise HTTPException(428, "Cần If-Match từ phiên bản danh mục hiện tại.")
            existing = session.scalar(
                select(AcceptedTarget).where(
                    AcceptedTarget.recommendation_id == proposal.id,
                    AcceptedTarget.owner_user_id == user_id,
                )
            )
            if existing:
                response.headers["ETag"] = f'"{value.version}"'
                return target_json(existing)
            if if_match != f'"{value.version}"':
                raise HTTPException(412, "Danh mục đã thay đổi, hãy tải lại.")
            job = session.scalar(
                select(Job).where(
                    Job.id == proposal.job_id, Job.owner_user_id == user_id
                )
            )
            if (
                not job
                or job.status != "SUCCEEDED"
                or job.input["portfolio_version"] != value.version
            ):
                raise HTTPException(
                    409, "Đề xuất không còn phù hợp với phiên bản danh mục."
                )
            try:
                if (
                    aware(datetime.fromisoformat((job.input.get("selection_context") or job.input["inputs"])["valid_until"]))
                    <= utcnow()
                ):
                    raise ValueError("expired")
                numerical = proposal.result | {
                    "weights": [float(w) for w in proposal.result["weights"]]
                }
                validate_result(numerical, job.input, resolver=resolver, deadline=min(aware(job.deadline), utcnow() + timedelta(seconds=15)) if not job.input.get("selection_context") else utcnow() + timedelta(seconds=15))
            except (ValueError, TypeError, KeyError):
                raise HTTPException(
                    409, "Đề xuất hết hạn hoặc không hợp lệ; hãy tạo đề xuất mới."
                ) from None
            value.version += 1
            target = AcceptedTarget(
                recommendation_id=proposal.id,
                portfolio_id=value.id,
                owner_user_id=user_id,
                portfolio_version=value.version,
                allocation=proposal.result,
            )
            session.add(target)
            session.flush()
            response.headers["ETag"] = f'"{value.version}"'
            return target_json(target)

    @app.get("/api/v1/portfolios/{portfolio_id}")
    def get_portfolio(portfolio_id: UUID, response: Response, user_id=Depends(owner)):
        with sessions() as session:
            value = session.scalar(
                select(Portfolio).where(
                    Portfolio.id == str(portfolio_id),
                    Portfolio.owner_user_id == user_id,
                )
            )
            if not value:
                raise HTTPException(404, "Không tìm thấy danh mục.")
            response.headers["ETag"] = f'"{value.version}"'
            return portfolio_json(value)

    @app.patch("/api/v1/portfolios/{portfolio_id}")
    def update_portfolio(
        portfolio_id: UUID,
        body: PortfolioUpdate,
        response: Response,
        user_id=Depends(owner),
        if_match: str | None = Header(default=None),
    ):
        updates = body.model_dump(exclude_unset=True)
        if not updates or any(value is None for value in updates.values()):
            raise HTTPException(422, "Cần ít nhất một giá trị cập nhật hợp lệ.")
        with sessions.begin() as session:
            value = session.scalar(
                select(Portfolio)
                .where(
                    Portfolio.id == str(portfolio_id),
                    Portfolio.owner_user_id == user_id,
                )
                .with_for_update()
            )
            if not value:
                raise HTTPException(404, "Không tìm thấy danh mục.")
            if if_match is None:
                raise HTTPException(428, "Cần If-Match từ phiên bản danh mục hiện tại.")
            if if_match != f'"{value.version}"':
                raise HTTPException(412, "Danh mục đã thay đổi, hãy tải lại.")
            if "name" in updates:
                value.name = updates["name"].strip()
            if "capital_vnd" in updates:
                value.capital_vnd = updates["capital_vnd"]
            value.constraints = value.constraints | {
                key: updates[key]
                for key in ("risk_aversion", "max_position_weight")
                if key in updates
            }
            value.constraints = effective_constraints(
                Constraints.model_validate(value.constraints), value.universe_id
            ).model_dump()
            if {"risk_aversion", "max_position_weight"}.intersection(updates):
                value.risk_profile = None
            value.version += 1
            response.headers["ETag"] = f'"{value.version}"'
            return portfolio_json(value)

    @app.get("/api/v1/portfolios/{portfolio_id}/recommendations")
    def list_recommendations(
        portfolio_id: UUID,
        response: Response,
        limit: int = Query(default=100, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=1_000_000),
        user_id=Depends(owner),
    ):
        with sessions() as session:
            portfolio = session.scalar(
                select(Portfolio).where(
                    Portfolio.id == str(portfolio_id),
                    Portfolio.owner_user_id == user_id,
                )
            )
            if not portfolio:
                raise HTTPException(404, "Không tìm thấy danh mục.")
            query = (
                select(Recommendation, Job)
                .join(Job, Job.id == Recommendation.job_id)
                .where(
                    Recommendation.portfolio_id == portfolio.id,
                    Recommendation.owner_user_id == user_id,
                    Job.owner_user_id == user_id,
                )
            )
            page_headers(response, session, query, limit, offset)
            return [
                recommendation_json(value, job)
                for value, job in session.execute(
                    query.order_by(
                        Recommendation.created_at.desc(), Recommendation.id.asc()
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ]

    def accepted(job):
        return {
            "job_id": job.id,
            "status_url": f"/api/v1/jobs/portfolio/{job.id}",
            **trace_fields(job.trace_context),
        }

    def recommendation_json(value, job):
        link_job(job.trace_context, job.id)
        return value.result | {
            "id": value.id,
            "portfolio_id": value.portfolio_id,
            "run_id": value.run_id,
            **trace_fields(job.trace_context),
        }

    @app.post("/api/v1/portfolios/{portfolio_id}/recommendations", status_code=202)
    def recommend(
        portfolio_id: UUID,
        body: NewRecommendation,
        user_id=Depends(owner),
        idempotency_key: str | None = Header(default=None),
        expected_chat_version: int | None = None,
        expected_chat_policy: str | None = None,
        if_match: Annotated[str | None, Header()] = None,
    ):
        if (
            not idempotency_key
            or not 1 <= len(idempotency_key) <= 128
            or any(ord(c) < 33 or ord(c) > 126 for c in idempotency_key)
        ):
            raise HTTPException(400, "Cần Idempotency-Key hợp lệ (1–128 ký tự ASCII).")
        system = body.mode == "system"
        payload = {"mode": "system"} if system else body.model_dump(exclude_none=True)
        if system and {"strategy", "fallback_strategy"} & body.model_fields_set:
            raise HTTPException(422, "Đề xuất hệ thống không nhận chiến lược hoặc phương án dự phòng.")
        if expected_chat_version is not None or expected_chat_policy is not None:
            payload['chat_confirmation'] = {'portfolio_version': expected_chat_version, 'policy_version_id': expected_chat_policy}
        body_hash = canonical_hash(payload)
        with sessions.begin() as session:
            # NO KEY UPDATE serializes the owner's quota without blocking FK
            # KEY SHARE checks when a result inserts its Recommendation.
            session.scalar(
                select(User).where(User.id == user_id).with_for_update(key_share=True)
            )
            portfolio = session.scalar(
                select(Portfolio)
                .where(
                    Portfolio.id == str(portfolio_id),
                    Portfolio.owner_user_id == user_id,
                )
                .with_for_update()
            )
            if not portfolio:
                raise HTTPException(404, "Không tìm thấy danh mục.")
            revision = current_selection(portfolio)
            if revision is not None:
                if_match = if_match or (f'"{expected_chat_version}"' if expected_chat_version is not None else None)
                if if_match is None:
                    raise HTTPException(428, "Cần If-Match từ phiên bản danh mục hiện tại.")
                body_hash = canonical_hash(payload | {"selection_portfolio_version": if_match})
            existing = session.scalar(
                select(Job).where(
                    Job.owner_user_id == user_id,
                    Job.portfolio_id == portfolio.id,
                    Job.idempotency_key == idempotency_key,
                )
            )
            if existing:
                if existing.body_hash != body_hash:
                    raise HTTPException(
                        409, "Idempotency-Key đã dùng cho nội dung khác."
                    )
                log_event(
                    "portfolio.job.accept", job_id=existing.id, outcome="duplicate"
                )
                return accepted(existing)
            if (system and not system_hybrid_enabled()) or (not system and system_hybrid_managed()):
                raise HTTPException(409, {"code": "INPUT_UNAVAILABLE", "message": "Yêu cầu tạo đề xuất chưa phù hợp với chế độ đang phục vụ."})
            if system and revision is None:
                raise HTTPException(409, {"code": "ASSET_SELECTION_REQUIRED", "message": "Cần tạo danh mục có rổ tài sản được chọn để tính đề xuất hệ thống."})
            if (expected_chat_version is not None and portfolio.version != expected_chat_version) or (expected_chat_policy is not None and policy_id(portfolio) != expected_chat_policy):
                raise HTTPException(409, "Danh mục/hồ sơ thay đổi; cần xác nhận lại.")
            if revision is not None:
                require_enabled()
                if if_match != f'"{portfolio.version}"':
                    raise HTTPException(412, "Danh mục đã thay đổi, hãy tải lại.")
            pending = session.scalar(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.owner_user_id == user_id,
                    Job.status == "QUEUED",
                    Job.deadline > utcnow(),
                )
            )
            if pending >= 5:
                raise HTTPException(
                    429, "Tối đa 5 yêu cầu đang chờ cho mỗi người dùng."
                )
            requested_strategy = "HYBRID" if system else body.strategy
            effective_strategy, fallback_reason = requested_strategy, None
            blend_policy = None
            selection_context = None
            constraints = None
            if revision is not None:
                readiness = selected_readiness(portfolio, revision)
                if system:
                    readiness = hybrid_readiness(readiness)
                by_strategy = {item.strategy: item for item in readiness.strategies}
                selected = by_strategy.get(requested_strategy)
                if selected and not selected.can_submit and body.strategy == "BL_ML" and body.fallback_strategy == "EW" and selected.reason_code in {
                    "MODEL_UNAVAILABLE", "MODEL_REVIEW_PENDING", "MODEL_COVERAGE_MISSING", "MODEL_EPOCH_MISMATCH", "NO_VALID_ML_VIEWS"
                } and by_strategy.get("EW") and by_strategy["EW"].can_submit:
                    effective_strategy, fallback_reason = "EW", selected.reason_code
                    selected = by_strategy["EW"]
                if not selected or not selected.can_submit or readiness.inputs is None or readiness.regime is None:
                    reason = selected.reason_code if selected else readiness.reason_code
                    details = stale_selection_details(readiness, reason)
                    message = "Lựa chọn chưa đủ điều kiện tính toán."
                    if details:
                        message = f"{details['asset_id']}: observation đủ điều kiện ngày {details['observation_date']} đã {details['age_days']} ngày; tối đa 7 ngày."
                    raise HTTPException(409, {"code": reason, "message": message, "details": details})
                constraints = effective_constraints(Constraints.model_validate(portfolio.constraints), "USER_SELECTED", readiness.regime.regime)
                if readiness.effective_constraints != constraints:
                    raise HTTPException(409, {"code": "INPUT_INVALID", "message": "Policy hiệu lực không khớp."})
                if system:
                    from portfolio_contracts.hybrid import hybrid_policy

                    blend_policy = hybrid_policy(readiness.regime.regime, portfolio.risk_profile.get("profile"))
                try:
                    selection_context = SelectionContext(
                        revision_id=revision.id, candidate_asset_ids=revision.candidate_asset_ids,
                        candidate_hash=revision.candidate_hash, regime=readiness.regime,
                        regime_input_hash=readiness.regime_input_hash, decision_at=readiness.decision_at,
                        decision_session=readiness.decision_session, valid_until=readiness.selection_valid_until,
                        data_policy_id=(readiness.inputs.provenance or {}).get("data_policy_id", "user-selection-data-v1"),
                    )
                except ValueError:
                    raise HTTPException(409, {"code": "INPUT_INVALID", "message": "Selection input không hợp lệ."}) from None
                if selection_context.valid_until <= utcnow():
                    raise HTTPException(409, {"code": "INPUT_EXPIRED", "message": "Dữ liệu lựa chọn đã hết hạn."})
                inputs = readiness.inputs
            else:
                try:
                    with span(
                        "portfolio.inputs.resolve", attributes={"strategy": body.strategy}
                    ):
                        try:
                            resolved = resolver.ready(portfolio.universe_id, body.strategy)
                        except ModelUnavailable:
                            if body.strategy != "BL_ML" or body.fallback_strategy != "EW":
                                raise
                            resolved = resolver.ready(portfolio.universe_id, "EW")
                            effective_strategy, fallback_reason = "EW", "MODEL_UNAVAILABLE"
                        inputs = ReadyInput.model_validate(resolved)
                except (httpx.HTTPError, ValueError, KeyError):
                    raise HTTPException(
                        503, "Chưa có dữ liệu/model phù hợp sẵn sàng."
                    ) from None
            if inputs.valid_until <= utcnow():
                raise HTTPException(409, "Dữ liệu đầu vào đã hết hạn.")
            phase = (inputs.provenance or {}).get("phase1_full")
            if portfolio.universe_id == "VN_PHASE1_FULL" and not phase:
                raise HTTPException(503, "Thiếu selection và policy của bộ tài sản đầy đủ.")
            if constraints is None:
                constraints = effective_constraints(
                    Constraints.model_validate(portfolio.constraints), portfolio.universe_id,
                    (phase or {}).get("regime", {}).get("regime", "normal"),
                )
            if (
                len(phase["active_asset_ids"] if phase and effective_strategy == "BL_ML" else inputs.asset_ids) * constraints.max_position_weight
                < 1 - 1e-8
            ) or (
                portfolio.universe_id == "VN_PHASE1_FULL"
                and constraints.max_position_weight + 1e-8 < max(
                    constraints.min_defensive_weight, 1 - constraints.max_non_defensive_weight
                )
            ):
                raise HTTPException(
                    409, "Giới hạn tỷ trọng không tạo được danh mục khả thi."
                )
            job_id = str(uuid4())
            command = OptimizeCommand(
                job_id=job_id,
                owner_user_id=user_id,
                portfolio_id=portfolio.id,
                portfolio_version=portfolio.version,
                strategy=effective_strategy,
                capital_vnd=str(portfolio.capital_vnd),
                inputs=inputs,
                constraints=constraints,
                selection_context=selection_context,
                hybrid_policy=blend_policy,
                decision_context=DecisionContext(
                    policy_version_id=policy_id(portfolio),
                    risk_profile=portfolio.risk_profile,
                    requested_strategy=requested_strategy,
                    fallback_reason=fallback_reason,
                    requested_constraints=portfolio.constraints if phase or revision is not None else None,
                ),
                deadline=min(utcnow() + timedelta(seconds=60), selection_context.valid_until) if selection_context is not None else utcnow() + timedelta(seconds=60),
                input_hash="0" * 64,
            )
            command.input_hash = command.compute_hash()
            event = Envelope(
                type="quant.optimize.requested",
                producer="portfolio",
                correlation_id=job_id,
                payload=command.model_dump(mode="json"),
            )
            with span(
                "portfolio.job.persist",
                attributes={"job.id": job_id, "event.id": event.event_id},
            ):
                context = capture_context()
                job = Job(
                    id=job_id,
                    owner_user_id=user_id,
                    portfolio_id=portfolio.id,
                    idempotency_key=idempotency_key,
                    body_hash=body_hash,
                    input_hash=command.input_hash,
                    input=command.model_dump(mode="json"),
                    deadline=command.deadline,
                    trace_context=context,
                )
                session.add_all(
                    [
                        job,
                        Outbox(
                            event_id=event.event_id,
                            payload=event.model_dump(mode="json"),
                            trace_context=context,
                        ),
                    ]
                )
                session.flush()
                log_event(
                    "portfolio.job.persist",
                    job_id=job_id,
                    event_id=event.event_id,
                    status="QUEUED",
                )
            return accepted(job)

    @app.get("/api/v1/jobs/portfolio/{job_id}")
    def get_job(job_id: UUID, user_id=Depends(owner)):
        with sessions.begin() as session:
            job = session.scalar(
                select(Job)
                .where(Job.id == str(job_id), Job.owner_user_id == user_id)
                .with_for_update()
            )
            if not job:
                raise HTTPException(404, "Không tìm thấy tác vụ.")
            link_job(job.trace_context, job.id)
            if job.status == "QUEUED" and aware(job.deadline) <= utcnow():
                job.status, job.error = (
                    "FAILED",
                    {
                        "code": "DEADLINE_EXCEEDED",
                        "message": "Quá thời hạn xử lý. Có thể tạo yêu cầu mới.",
                    },
                )
            return {
                "job_id": job.id,
                "status": job.status,
                "recommendation_id": job.recommendation_id,
                "error": job.error,
                **trace_fields(job.trace_context),
            }

    @app.get("/api/v1/recommendations/{recommendation_id}")
    def get_recommendation(recommendation_id: UUID, user_id=Depends(owner)):
        with sessions() as session:
            value = session.scalar(
                select(Recommendation).where(
                    Recommendation.id == str(recommendation_id),
                    Recommendation.owner_user_id == user_id,
                )
            )
            if not value:
                raise HTTPException(404, "Không tìm thấy đề xuất.")
            job = session.scalar(
                select(Job).where(Job.id == value.job_id, Job.owner_user_id == user_id)
            )
            if job is None:
                raise HTTPException(404, "Không tìm thấy tác vụ.")
            return recommendation_json(value, job)

    @app.get("/api/v1/recommendations/{recommendation_id}/evidence", response_model=RecommendationEvidence)
    def get_recommendation_evidence(recommendation_id: UUID, user_id=Depends(owner)):
        from .explanation import recommendation_evidence

        with sessions() as session:
            value = session.scalar(select(Recommendation).where(
                Recommendation.id == str(recommendation_id), Recommendation.owner_user_id == user_id))
            if not value:
                raise HTTPException(404, "Không tìm thấy đề xuất.")
            job = session.get(Job, value.job_id)
            if not job or job.owner_user_id != user_id:
                raise HTTPException(404, "Không tìm thấy đề xuất.")
            return recommendation_evidence(value, job, recommendation_json(value, job))

    from .delegation import install
    install(app, sessions=sessions, verifier=verifier, principal=principal, owner=owner,
            owned_portfolio=owned_portfolio, portfolio_json=portfolio_json,
            recommend=recommend, recommendation_json=recommendation_json,
            recommendation_type=NewRecommendation, account_active=account_active)
    return app
