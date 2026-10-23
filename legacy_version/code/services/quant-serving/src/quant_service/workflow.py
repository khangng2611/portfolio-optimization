from uuid import uuid4

from sqlalchemy import select, text

from portfolio_contracts import Envelope, OptimizeCommand, OptimizeResult, utcnow
from portfolio_core import CoreError, allocate
from .models import Inbox, Outbox, Run


def execute(sessions, catalog, event: Envelope):
    if event.type != "quant.optimize.requested" or event.producer != "portfolio":
        raise ValueError("Unexpected producer/type")
    command = OptimizeCommand.model_validate(event.payload)
    if (
        event.correlation_id != command.job_id
        or command.compute_hash() != command.input_hash
    ):
        raise ValueError("Input hash/correlation mismatch")
    with sessions.begin() as session:
        # Serialize duplicate logical jobs across worker replicas, including the first insert.
        if session.bind.dialect.name == "postgresql":
            lock_key = int.from_bytes(command.job_id.bytes[:8], signed=True)
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key}
            )
        existing = session.scalar(select(Run).where(Run.job_id == str(command.job_id)))
        if existing and existing.input_hash != command.input_hash:
            raise ValueError("Job identity reused with different inputs")
        if session.get(Inbox, event.event_id):
            return
        session.add(Inbox(event_id=event.event_id))
        if existing:
            return
        run_id = str(uuid4())
        result, error = None, None
        try:
            if command.deadline <= utcnow():
                raise ValueError("Command deadline exceeded")
            numerical = catalog.load(command.inputs, command.strategy)
            result = allocate(
                numerical
                | {
                    "strategy": command.strategy,
                    "constraints": command.constraints.model_dump(),
                }
            )
            if command.deadline <= utcnow():
                raise ValueError("Computation exceeded deadline")
        except CoreError as exc:
            error = {"code": exc.code, "message": exc.message}
        except ValueError as exc:
            error = {"code": "INPUT_UNAVAILABLE", "message": str(exc)}
        payload = OptimizeResult(
            job_id=command.job_id,
            input_hash=command.input_hash,
            run_id=run_id,
            bundle_hash=command.inputs.bundle_hash,
            status="FAILED" if error else "SUCCEEDED",
            result=None if error else result,
            error=error,
        )
        completion = Envelope(
            type="quant.optimization.completed",
            producer="quant-serving",
            correlation_id=command.job_id,
            payload=payload.model_dump(mode="json"),
        )
        session.add_all(
            [
                Run(
                    id=run_id,
                    job_id=str(command.job_id),
                    input_hash=command.input_hash,
                    payload=payload.model_dump(mode="json"),
                ),
                Outbox(
                    event_id=completion.event_id,
                    payload=completion.model_dump(mode="json"),
                ),
            ]
        )
