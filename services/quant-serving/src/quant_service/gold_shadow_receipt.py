"""Single wire representation for a proposal observed after its issuance transaction."""

from datetime import datetime, timezone

from portfolio_contracts import aware, canonical_hash


def confirmed_receipt(receipt, witnessed_at, receipt_sha256):
    result = dict(receipt)
    original = result.pop("receipt_sha256")
    if original != receipt_sha256 or original != canonical_hash(result):
        raise ValueError("Durability witness does not match the original decision")
    witnessed = aware(witnessed_at).astimezone(timezone.utc)
    if witnessed < datetime.fromisoformat(result["issued_at"]):
        reason = "WITNESS_CLOCK_BEFORE_ISSUANCE"
    elif result.get("issue_before") and witnessed >= datetime.fromisoformat(
        result["issue_before"]
    ):
        reason = "DURABILITY_WITNESSED_AFTER_WINDOW"
    else:
        reason = None
    if reason:
        if result["status"] == "TARGET" or result.get("reason") == "calibration_warmup":
            result.update(status="ABSTAIN", reason=reason)
        result.pop("forecast", None)
        result["shadow_weights"] = None
    result.update(issued_receipt_sha256=original, witnessed_at=witnessed.isoformat())
    result["receipt_sha256"] = canonical_hash(result)
    return result
