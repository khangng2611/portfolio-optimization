"""Owner service authorization for delayed Chat tools. Tokens are never persisted."""

from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from pydantic import Field
from sqlalchemy import select, update

from portfolio_contracts import StrictModel, aware, canonical_hash, utcnow
from service_auth import AuthError
from .models import DelegationGrant, Job, Recommendation, User

Tool = Literal[
    "get_profile",
    "get_portfolio_summary",
    "request_allocation",
    "get_recommendation",
    "get_allocation_job",
]


class GrantRequest(StrictModel):
    conversation_id: UUID
    job_id: UUID
    authorization_id: UUID | None = None
    portfolio_id: UUID | None = None
    tools: list[Tool] = Field(min_length=1, max_length=5)


class ToolArguments(StrictModel):
    portfolio_id: UUID | None = None
    resource_id: UUID | None = None
    strategy: Literal["EW", "MVO", "BL_ML"] | None = None
    expected_version: int | None = Field(default=None, ge=1)
    expected_policy_version: str | None = Field(default=None, max_length=128)


def install(
    app,
    *,
    sessions,
    verifier,
    principal,
    owner,
    owned_portfolio,
    portfolio_json,
    recommend,
    recommendation_json,
    recommendation_type,
    account_active,
):
    def actor_token(token):
        try:
            if not token or not token.startswith("Bearer "):
                raise AuthError("Missing service identity")
            actor = verifier.verify(token[7:])
        except AuthError:
            raise HTTPException(401, "Cần service identity hợp lệ.") from None
        if actor.client_id != "chat-service" or "chat:delegate" not in actor.scopes:
            raise HTTPException(403, "Service không được phép dùng Chat tools.")
        return actor

    def actor(authorization: str | None = Header(default=None)):
        return actor_token(authorization)

    @app.post("/internal/v1/delegation-grants")
    def issue(
        body: GrantRequest,
        identity=Depends(principal),
        user_id=Depends(owner),
        x_service_authorization: str | None = Header(default=None),
    ):
        who = actor_token(x_service_authorization)
        if "portfolio:read" not in identity.scopes or (
            "request_allocation" in body.tools
            and "portfolio:write" not in identity.scopes
        ):
            raise HTTPException(403, "Thiếu scope của người dùng.")
        digest = canonical_hash(body.model_dump(mode="json"))
        with sessions.begin() as s:
            s.scalar(select(User).where(User.id == user_id).with_for_update())
            if body.portfolio_id:
                owned_portfolio(s, body.portfolio_id, user_id)
            grant = s.scalar(
                select(DelegationGrant).where(
                    DelegationGrant.owner_user_id == user_id,
                    DelegationGrant.chat_job_id == str(body.job_id),
                    DelegationGrant.authorization_id
                    == (
                        str(body.authorization_id)
                        if body.authorization_id
                        else "initial"
                    ),
                )
            )
            if grant and grant.body_hash != digest:
                raise HTTPException(409, "Job đã có delegation khác.")
            if not grant:
                grant = DelegationGrant(
                    owner_user_id=user_id,
                    actor=who.client_id,
                    conversation_id=str(body.conversation_id),
                    chat_job_id=str(body.job_id),
                    authorization_id=str(body.authorization_id)
                    if body.authorization_id
                    else "initial",
                    portfolio_id=str(body.portfolio_id) if body.portfolio_id else None,
                    tools=sorted(set(body.tools)),
                    body_hash=digest,
                    expires_at=utcnow() + timedelta(minutes=5),
                )
                s.add(grant)
                s.flush()
            # Replaying a grant request never extends its lifetime or clears revocation.
            return {
                "grant_id": grant.id,
                "job_id": grant.chat_job_id,
                "conversation_id": grant.conversation_id,
                "expires_at": aware(grant.expires_at).isoformat(),
            }

    @app.post("/api/v1/chat/delegations/revoke")
    def revoke(body: StrictModel, user_id=Depends(owner)):
        with sessions.begin() as s:
            s.execute(
                update(DelegationGrant)
                .where(
                    DelegationGrant.owner_user_id == user_id,
                    DelegationGrant.revoked_at.is_(None),
                )
                .values(revoked_at=utcnow())
            )
        return {"revoked": True}

    @app.post("/internal/v1/chat-tools/{tool}")
    def invoke(
        tool: str,
        body: ToolArguments,
        who=Depends(actor),
        x_delegation_grant: str | None = Header(default=None),
        x_chat_job: str | None = Header(default=None),
        x_chat_conversation: str | None = Header(default=None),
    ):
        if tool not in Tool.__args__:
            raise HTTPException(404, "Tool không được phép.")
        # Hold grant lock across tool execution: revoke cannot race an authorized mutation.
        with sessions.begin() as s:
            g = s.scalar(
                select(DelegationGrant)
                .where(DelegationGrant.id == x_delegation_grant)
                .with_for_update()
            )
            if (
                not g
                or g.actor != who.client_id
                or g.chat_job_id != x_chat_job
                or g.conversation_id != x_chat_conversation
                or g.revoked_at
                or aware(g.expires_at) <= utcnow()
                or tool not in g.tools
            ):
                raise HTTPException(
                    403, "Delegation hết hạn, bị thu hồi hoặc không đúng binding."
                )
            user = s.get(User, g.owner_user_id)
            if not account_active or not account_active(user.issuer, user.subject):
                raise HTTPException(403, "Tài khoản không còn quyền truy cập.")
            if body.portfolio_id and str(body.portfolio_id) != g.portfolio_id:
                raise HTTPException(403, "Resource không thuộc delegation.")
            if tool == "get_profile":
                return {
                    "id": user.id,
                    "portfolio": portfolio_json(
                        owned_portfolio(s, g.portfolio_id, user.id)
                    )
                    if g.portfolio_id
                    else None,
                }
            if not g.portfolio_id:
                raise HTTPException(403, "Delegation chưa chọn danh mục.")
            p = owned_portfolio(s, g.portfolio_id, user.id)
            if tool == "get_portfolio_summary":
                return portfolio_json(p)
            if tool == "request_allocation":
                if (
                    body.expected_version is None
                    or not body.expected_policy_version
                    or not body.strategy
                ):
                    raise HTTPException(
                        422, "Cần phiên bản, policy và chiến lược đã xác nhận."
                    )
                # The owner use case resolves durable idempotency before checking
                # current versions. A prior committed request remains reconcilable
                # after portfolio edits; a new request checks pins under its lock.
                return recommend(
                    UUID(p.id),
                    recommendation_type(strategy=body.strategy),
                    user_id=user.id,
                    idempotency_key="chat-" + g.chat_job_id,
                    expected_chat_version=body.expected_version,
                    expected_chat_policy=body.expected_policy_version,
                )
            if not body.resource_id:
                raise HTTPException(422, "Cần resource_id.")
            job = (
                s.get(Job, str(body.resource_id))
                if tool == "get_allocation_job"
                else None
            )
            r = (
                s.get(Recommendation, str(body.resource_id))
                if tool == "get_recommendation"
                else None
            )
            resource = job or r
            if (
                not resource
                or resource.owner_user_id != user.id
                or resource.portfolio_id != p.id
            ):
                raise HTTPException(404, "Không tìm thấy resource thuộc delegation.")
            if job:
                return {
                    "job_id": job.id,
                    "status": job.status,
                    "recommendation_id": job.recommendation_id,
                    "error": job.error,
                }
            return recommendation_json(r, s.get(Job, r.job_id))
