from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field, StringConstraints
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

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
    User,
)
from .policy import RiskAnswers, risk_policy
from .workflow import validate_result

HUMAN_ROLES = {
    "investor",
    "researcher",
    "data-operator",
    "model-reviewer",
    "system-admin",
}


class NewPortfolio(StrictModel):
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


class OnboardingPortfolio(StrictModel):
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
    ]


class InputReadiness(StrictModel):
    # Additive diagnostics only: immutable ReadyInput execution pins are unchanged.
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
    reason_code: Literal["READY", "INPUT_EXPIRED", "INPUT_UNAVAILABLE", "INPUT_INVALID"]
    strategies: list[StrategyReadiness]
    next_action: Literal["NONE", "REFRESH_DATA", "CONTACT_OPERATOR"]
    checked_at: datetime


def profile_policy_id(profile):
    if not profile:
        return "manual-constraints-v1"
    legacy = f"risk-policy-v1:{profile['profile']}"
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
    return {
        "id": value.id,
        "name": value.name,
        "capital_vnd": str(value.capital_vnd),
        "universe_id": value.universe_id,
        "constraints": value.constraints,
        "version": value.version,
        "policy_version_id": policy_id(value),
        "risk_profile": value.risk_profile,
    }


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

    def error(request, status, code, message, headers=None):
        return JSONResponse(
            status_code=status,
            content={
                "error": {"code": code, "message": message, "retryable": status == 503},
                "request_id": request.state.request_id,
            },
            headers=headers,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
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

    @app.post("/api/v1/portfolios", status_code=201)
    def create_portfolio(body: NewPortfolio, user_id=Depends(owner)):
        with sessions.begin() as session:
            value = Portfolio(
                owner_user_id=user_id,
                name=body.name.strip(),
                capital_vnd=body.capital_vnd,
                universe_id=body.universe_id,
                constraints=Constraints(
                    risk_aversion=body.risk_aversion,
                    max_position_weight=body.max_position_weight,
                ).model_dump(),
            )
            session.add(value)
            session.flush()
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
        profile, constraints = risk_policy(body.answers)
        with sessions.begin() as session:
            value = Portfolio(
                owner_user_id=user_id,
                name=body.name.strip(),
                capital_vnd=body.capital_vnd,
                universe_id=body.universe_id,
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
            return portfolio_json(value)

    def owned_portfolio(session, portfolio_id, user_id, *, lock=False):
        query = select(Portfolio).where(
            Portfolio.id == str(portfolio_id), Portfolio.owner_user_id == user_id
        )
        value = session.scalar(query.with_for_update() if lock else query)
        if value is None:
            raise HTTPException(404, "Không tìm thấy danh mục.")
        return value

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
        profile, constraints = risk_policy(body.answers)
        with sessions() as session:
            value = owned_portfolio(session, portfolio_id, user_id)
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
        profile, constraints = risk_policy(body.answers)
        body_hash = canonical_hash(body.model_dump())
        with sessions.begin() as session:
            value = owned_portfolio(session, portfolio_id, user_id, lock=True)
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

    @app.get(
        "/api/v1/portfolios/{portfolio_id}/readiness", response_model=InputReadiness
    )
    def portfolio_readiness(portfolio_id: UUID, user_id=Depends(owner)):
        with sessions() as session:
            value = owned_portfolio(session, portfolio_id, user_id)
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
                    aware(datetime.fromisoformat(job.input["inputs"]["valid_until"]))
                    <= utcnow()
                ):
                    raise ValueError("expired")
                numerical = proposal.result | {
                    "weights": [float(w) for w in proposal.result["weights"]]
                }
                validate_result(numerical, job.input)
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
    ):
        if (
            not idempotency_key
            or not 1 <= len(idempotency_key) <= 128
            or any(ord(c) < 33 or ord(c) > 126 for c in idempotency_key)
        ):
            raise HTTPException(400, "Cần Idempotency-Key hợp lệ (1–128 ký tự ASCII).")
        payload = body.model_dump(exclude_none=True)
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
            if (expected_chat_version is not None and portfolio.version != expected_chat_version) or (expected_chat_policy is not None and policy_id(portfolio) != expected_chat_policy):
                raise HTTPException(409, "Danh mục/hồ sơ thay đổi; cần xác nhận lại.")
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
            effective_strategy, fallback_reason = body.strategy, None
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
            if (
                len(inputs.asset_ids) * portfolio.constraints["max_position_weight"]
                < 1 - 1e-8
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
                constraints=portfolio.constraints,
                decision_context=DecisionContext(
                    policy_version_id=policy_id(portfolio),
                    risk_profile=portfolio.risk_profile,
                    requested_strategy=body.strategy,
                    fallback_reason=fallback_reason,
                ),
                deadline=utcnow() + timedelta(seconds=60),
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

    from .delegation import install
    install(app, sessions=sessions, verifier=verifier, principal=principal, owner=owner,
            owned_portfolio=owned_portfolio, portfolio_json=portfolio_json,
            recommend=recommend, recommendation_json=recommendation_json,
            recommendation_type=NewRecommendation, account_active=account_active)
    return app
