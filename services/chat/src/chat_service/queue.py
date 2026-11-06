from datetime import timedelta
from uuid import uuid4
from sqlalchemy import and_, or_, select, update
from portfolio_contracts import utcnow
from .models import Event, Job, Message

TERMINAL = {
    "SUCCEEDED",
    "FAILED",
    "WAITING_INPUT",
    "AUTHORIZATION_REQUIRED",
    "CANCELLED",
}


def append_event(s, job, kind, payload):
    job.event_sequence += 1
    s.add(Event(job_id=job.id, sequence=job.event_sequence, type=kind, payload=payload))


class Queue:
    def __init__(self, sessions):
        self.sessions = sessions

    def claim(self, *, now=None):
        now = now or utcnow()
        eligible = or_(
            and_(
                Job.status.in_(["QUEUED", "RETRY", "WAITING_DEPENDENCY"]),
                Job.next_attempt_at <= now,
            ),
            and_(Job.status == "RUNNING", Job.lease_until <= now),
        )
        with self.sessions.begin() as s:
            jid = s.scalar(
                select(Job.id)
                .where(eligible)
                .order_by(Job.created_at, Job.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if not jid:
                return None
            token = str(uuid4())
            r = s.execute(
                update(Job)
                .where(Job.id == jid, eligible)
                .values(
                    status="RUNNING",
                    lease_token=token,
                    lease_until=now + timedelta(seconds=30),
                )
            )
            if r.rowcount != 1:
                return None
            return s.get(Job, jid)

    def reserve_provider(self, job, *, now=None):
        now = now or utcnow()
        with self.sessions.begin() as s:
            result = s.execute(
                update(Job)
                .where(
                    Job.id == job.id,
                    Job.status == "RUNNING",
                    Job.lease_token == job.lease_token,
                    Job.lease_until > now,
                    Job.provider_calls < 1,
                )
                .values(provider_calls=Job.provider_calls + 1)
            )
            return result.rowcount == 1

    def finish(
        self,
        job,
        *,
        status,
        stage=None,
        error=None,
        message=None,
        events=(),
        dependency_id=None,
        recommendation_id=None,
        attempts=None,
        delay=0,
        now=None,
    ):
        now = now or utcnow()
        with self.sessions.begin() as s:
            # Conditional write fences SQLite too; row lock held through message/event commit.
            r = s.execute(
                update(Job)
                .where(
                    Job.id == job.id,
                    Job.status == "RUNNING",
                    Job.lease_token == job.lease_token,
                    Job.lease_until > now,
                )
                .values(lease_until=now + timedelta(seconds=30))
            )
            if r.rowcount != 1:
                return False
            current = s.get(Job, job.id)
            current.status, current.error = status, error
            current.stage = stage or current.stage
            current.lease_token, current.lease_until = None, None
            current.next_attempt_at = now + timedelta(seconds=delay)
            if dependency_id:
                current.dependency_id = dependency_id
            if recommendation_id:
                current.recommendation_id = recommendation_id
            if attempts is not None:
                current.attempts = attempts
            if message:
                s.add(
                    Message(
                        **message,
                        conversation_id=current.conversation_id,
                        role="assistant",
                    )
                )
                current.result_message_id = message["id"]
            for kind, payload in events:
                append_event(s, current, kind, payload)
            return True
