"""Select the policy for a new system proposal from operator-reviewed evidence."""
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from portfolio_contracts.hybrid import FORWARD_POLICY, SERVING_POLICY

FINAL_REPORT = Path("/run/hybrid-study/final.json")


def reviewed_version(now=None):
    expected = os.environ.get("HYBRID_REVIEWED_REPORT_SHA256")
    if expected is None:
        if os.environ.get("HYBRID_LOCAL_RETROSPECTIVE_POLICY") == FORWARD_POLICY:
            return FORWARD_POLICY
        return SERVING_POLICY
    now = now or datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    if now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat() <= "2027-11-30":
        return None
    try:
        content = FINAL_REPORT.read_bytes()
        if sha256(content).hexdigest() != expected:
            return None
        report = json.loads(content)
        if (report["status"] == "PASS" and report["policy"] == FORWARD_POLICY
                and report["evaluation_period"] == ["2026-11-24", "2027-11-23"]
                and report["informative_normal_executions"] > 0
                and all(report["checks"][p][key] is True for p in ("conservative", "balanced", "growth")
                        for key in ("drawdown", "turnover", "volatility"))):
            return FORWARD_POLICY
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return None
