from uuid import uuid4

from sqlalchemy import select, text

from portfolio_contracts import Envelope, OptimizeCommand, OptimizeResult, utcnow
from portfolio_core import CoreError, allocate
from service_observability import capture_context, link_job, log_event, span
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
    link_job(None, command.job_id)
    attributes = {"job.id": str(command.job_id), "event.id": str(event.event_id),
                  "strategy": command.strategy, "core.version": command.core_version}
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
            log_event("quant.command", job_id=str(command.job_id), event_id=str(event.event_id), outcome="duplicate_delivery")
            return
        session.add(Inbox(event_id=event.event_id))
        if existing:
            log_event("quant.command", job_id=str(command.job_id), event_id=str(event.event_id), outcome="duplicate_job")
            return
        run_id = str(uuid4())
        result, error = None, None
        try:
            if command.deadline <= utcnow():
                raise ValueError("Command deadline exceeded")
            with span("quant.inputs.load", attributes=attributes):
                numerical = catalog.load(command.inputs, command.strategy)
            with span("portfolio_core.allocate", attributes=attributes) as current:
                result = allocate(
                    numerical | {"strategy": command.strategy, "constraints": command.constraints.model_dump()}
                )
                current.set_attribute("status", result["status"])
            if command.deadline <= utcnow():
                raise ValueError("Computation exceeded deadline")
        except CoreError as exc:
            error = {"code": exc.code, "message": exc.message}
            log_event("quant.execution", job_id=str(command.job_id), event_id=str(event.event_id), status="FAILED", error_type=type(exc).__name__, error_code=exc.code)
        except ValueError as exc:
            error = {"code": "INPUT_UNAVAILABLE", "message": str(exc)}
            log_event("quant.execution", job_id=str(command.job_id), event_id=str(event.event_id), status="FAILED", error_type=type(exc).__name__, error_code="INPUT_UNAVAILABLE")
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
        context = capture_context()
        with span("quant.result.persist", attributes=attributes | {"status": payload.status}):
            session.add_all(
                [
                    Run(
                        id=run_id, job_id=str(command.job_id), input_hash=command.input_hash,
                        payload=payload.model_dump(mode="json"), trace_context=context,
                    ),
                    Outbox(event_id=completion.event_id, payload=completion.model_dump(mode="json"), trace_context=context),
                ]
            )
            session.flush()
            log_event("quant.result.persist", job_id=str(command.job_id), event_id=str(completion.event_id), status=payload.status)
