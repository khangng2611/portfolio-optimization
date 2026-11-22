from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_paid_preflight_requires_exact_approval_and_cap():
    from smoke_allocation_explanation import budget_preflight

    config = dict(
        enabled=True,
        embeddings_enabled=False,
        has_key=True,
        model="gpt-6-luna",
        approval="approved-old",
        budget="0.50",
        calls_limit=20,
        daily_limit=20,
    )
    usage = dict(reservations=2, reserved_usd="0.0034", estimated_usd="0.0002")
    assert budget_preflight(config, usage, "openai", "approved-old", "0.50")["allowed"]
    assert not budget_preflight(
        config | {"budget": "1.00"}, usage, "openai", "approved-old", "0.50"
    )["allowed"]
    assert not budget_preflight(config, usage, "openai", None, "0.50")["allowed"]
    assert not budget_preflight(
        config, usage | {"reserved_usd": "0.49"}, "openai", "approved-old", "0.50"
    )["allowed"]


def test_native_smoke_reuses_only_confirmed_source_profile_and_candidates():
    import pytest
    from smoke_allocation_explanation import onboarding_body

    source = {
        "capital_vnd": "100000000",
        "risk_profile": {
            "answers": {
                "questionnaire_version": "risk-v1",
                "horizon_months": 24,
                "liquidity_need": "high",
                "loss_tolerance": "low",
                "experience": "beginner",
            }
        },
        "asset_selection": {"candidate_asset_ids": ["ACB", "BID", "GOLD", "VFF"]},
    }
    body = onboarding_body("BL_ML", source)
    assert body["asset_ids"] == source["asset_selection"]["candidate_asset_ids"]
    assert body["answers"] == source["risk_profile"]["answers"]
    assert "universe_id" not in body
    assert body["name"].startswith("EXPLANATION TEST")
    with pytest.raises(ValueError):
        onboarding_body("BL_ML", source | {"risk_profile": None})


def test_reservation_alone_cannot_pass_paid_provider_gate():
    from smoke_allocation_explanation import paid_outcome

    cards = [
        {
            "job_id": "job",
            "card": {
                "explanation_status": "TEMPLATE",
                "provider": {"reason": "TIMEOUT"},
                "selected_claim_ids": ["profile"],
            },
        }
    ]
    usage = [
        {
            "job_id": "job",
            "purpose": "explanation",
            "reserved_usd": "0.0017",
            "usage": {"reason": "TIMEOUT"},
        }
    ]
    assert paid_outcome(cards, usage)["status"] == "FAIL"


def test_template_preflight_cannot_silently_use_enabled_server():
    from smoke_allocation_explanation import budget_preflight

    config = dict(enabled=True, embeddings_enabled=False, has_key=True)
    assert not budget_preflight(config, {}, "template")["allowed"]
    assert budget_preflight(config | {"enabled": False}, {}, "template")["allowed"]
    assert not budget_preflight(
        config | {"enabled": False, "embeddings_enabled": True}, {}, "template"
    )["allowed"]
