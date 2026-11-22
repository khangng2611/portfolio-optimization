"""Custom admission pins revision, TTL and effective policy before enqueue."""
from datetime import timedelta
import copy

import pytest
from sqlalchemy import select, func
from portfolio_contracts import utcnow, OptimizeCommand
from portfolio_contracts.assets import ASSET_IDS
from portfolio_service.models import Job, Outbox
from portfolio_service.policy import effective_constraints
from portfolio_contracts import Constraints
from test_workflow import Resolver, headers, stack as workflow_stack

from test_selected_portfolio import create
from test_chat_delegation import grants as delegation_grants, issue, tool

stack = workflow_stack
grants = delegation_grants


@pytest.mark.parametrize("policy", ["user-selection-live-nav-v2", "unknown-policy"])
def test_allocation_pins_verified_data_policy_or_rejects_unknown(stack, preflight, monkeypatch, policy):
    original = Resolver.selection_ready
    def ready(self, body):
        result = original(self, body)
        result["inputs"]["provenance"] = {"data_policy_id": policy}
        return result
    monkeypatch.setattr(Resolver, "selection_ready", ready)
    client, sessions = stack
    p = create(client, ["FPT", "VFF"]).json()
    response = client.post(
        f"/api/v1/portfolios/{p['id']}/recommendations",
        headers=headers(**{"If-Match": '"1"', "Idempotency-Key": "live-policy"}),
        json={"strategy": "MVO"},
    )
    if policy == "unknown-policy":
        assert response.status_code == 409
    else:
        assert response.status_code == 202, response.text
        with sessions() as session:
            command = OptimizeCommand.model_validate(session.get(Job, response.json()["job_id"]).input)
            assert command.selection_context.data_policy_id == policy
            assert command.compute_hash() == session.get(Job, response.json()["job_id"]).input_hash


@pytest.fixture
def preflight(monkeypatch):
    calls = []
    def ready(self, body):
        calls.append(copy.deepcopy(body))
        now = utcnow()
        return {
            'readiness_kind': 'user-selection-v1',
            'portfolio_version': body['portfolio_version'], 'revision_id': body['revision_id'],
            'candidate_hash': body['candidate_hash'], 'candidate_asset_ids': body['candidate_asset_ids'],
            'can_submit': True, 'reason_code': 'READY',
            'strategies': [{'strategy': s, 'can_submit': True, 'reason_code': 'READY'} for s in ['EW', 'MVO', 'BL_ML']],
            'asset_status': [], 'regime': {'regime': 'crisis', 'vol_ratio': 2., 'drawdown': -.2, 'equity_momentum': -.01},
            'regime_input_hash': 'c' * 64, 'decision_at': now.isoformat(), 'decision_session': str(now.date()),
            'selection_valid_until': (now + timedelta(seconds=30)).isoformat(),
            'effective_constraints': effective_constraints(Constraints.model_validate(body['constraints']), 'USER_SELECTED', 'crisis').model_dump(),
            'inputs': Resolver().legacy_ready('DEMO', 'MVO') | {'asset_ids': list(ASSET_IDS)},
            'checked_at': now.isoformat(),
        }
    monkeypatch.setenv('USER_SELECTED_ASSETS_ENABLED', 'true')
    monkeypatch.setattr(Resolver, 'legacy_ready', Resolver.ready, raising=False)
    monkeypatch.setattr(Resolver, 'selection_ready', ready, raising=False)
    return calls


def test_custom_job_pins_original_resource_revision_and_regime_with_replay(stack, preflight):
    client, sessions = stack
    p = create(client, ['FPT', 'MWG', 'VCB', 'VFF']).json()
    path = f"/api/v1/portfolios/{p['id']}/recommendations"
    h = headers(**{'If-Match': '"1"', 'Idempotency-Key': 'selected-job'})
    response = client.post(path, headers=h, json={'strategy': 'BL_ML'})
    assert response.status_code == 202, response.text
    jid = response.json()['job_id']
    with sessions() as session:
        job = session.get(Job, jid)
        command = OptimizeCommand.model_validate(job.input)
        assert command.inputs.asset_ids == list(ASSET_IDS)
        assert command.selection_context.candidate_asset_ids == ['FPT', 'MWG', 'VCB', 'VFF']
        assert str(command.selection_context.revision_id) == p['asset_selection']['revision_id']
        assert command.constraints.risk_aversion == 5
        assert command.decision_context.requested_constraints.risk_aversion == 3
        assert command.deadline <= command.selection_context.valid_until < command.inputs.valid_until
        assert command.compute_hash() == job.input_hash
        before = copy.deepcopy(job.input)
    assert len(preflight) == 1
    assert set(preflight[0]) == {'portfolio_version', 'revision_id', 'candidate_hash', 'candidate_asset_ids', 'constraints'}
    assert client.post(path, headers=h, json={'strategy': 'BL_ML'}).json() == response.json()
    assert len(preflight) == 1
    edited = client.post(f"/api/v1/portfolios/{p['id']}/asset-selections", headers=headers(**{'If-Match': '"1"', 'Idempotency-Key': 'edit'}), json={'candidate_asset_ids': ['GOLD', 'VFF']})
    assert edited.status_code == 201
    assert client.post(path, headers=h, json={'strategy': 'BL_ML'}).json() == response.json()
    assert client.post(path, headers=headers(**{'If-Match': '"2"', 'Idempotency-Key': 'selected-job'}), json={'strategy': 'BL_ML'}).status_code == 409
    with sessions() as session:
        assert session.get(Job, jid).input == before
        assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_system_mode_only_accepts_server_selected_hybrid(stack, preflight, monkeypatch):
    monkeypatch.setenv('SYSTEM_HYBRID_ENABLED', 'true')
    client, sessions = stack
    p = create(client, ['FPT', 'MWG', 'VCB', 'VFF']).json()
    base = f"/api/v1/portfolios/{p['id']}"
    ready = client.get(base + '/readiness', headers=headers()).json()
    assert ready['strategies'] == [{'strategy': 'HYBRID', 'can_submit': True, 'reason_code': 'READY'}]
    h = headers(**{'If-Match': '"1"', 'Idempotency-Key': 'system-allocation'})
    path = base + '/recommendations'
    assert client.post(path, headers=h, json={'strategy': 'MVO'}).status_code == 409
    assert client.post(path, headers=h, json={'mode': 'system', 'fallback_strategy': 'EW'}).status_code == 422
    result = client.post(path, headers=h, json={'mode': 'system'})
    assert result.status_code == 202, result.text
    assert client.post(path, headers=h, json={'mode': 'system'}).json() == result.json()
    with sessions() as session:
        job = session.get(Job, result.json()['job_id'])
        command = OptimizeCommand.model_validate(job.input)
        assert command.strategy == command.decision_context.requested_strategy == 'HYBRID'
        assert command.hybrid_policy.mvo_share == .10
        assert command.compute_hash() == job.input_hash
    monkeypatch.setenv('SYSTEM_HYBRID_ENABLED', 'paused')
    assert not client.get(base + '/readiness', headers=headers()).json()['can_submit']
    assert client.post(path, headers=h, json={'mode': 'system'}).json() == result.json()
    new_headers = h | {'Idempotency-Key': 'paused-new-job'}
    assert client.post(path, headers=new_headers, json={'mode': 'system'}).status_code == 409
    assert client.post(path, headers=new_headers, json={'strategy': 'EW'}).status_code == 409


@pytest.mark.parametrize('malformed', [False, True])
@pytest.mark.parametrize('fallback', [False, True])
def test_stale_candidate_blocks_without_outbox_even_with_ew_fallback(stack, monkeypatch, preflight, fallback, malformed):
    client, sessions = stack
    p = create(client, ['GOLD', 'VFF']).json()
    original = Resolver.selection_ready
    def stale(self, body):
        ready = original(self, body)
        ready.update(can_submit=False, reason_code='VFF_STALE', inputs=None, asset_status=[{'asset_id': 'VFF', 'observation_date': '2026-11-03', 'age_days': True if malformed else 8, 'max_age_days': 7, 'private_path': '/private/secret'}])
        ready['strategies'] = [{'strategy': s, 'can_submit': False, 'reason_code': 'VFF_STALE'} for s in ['EW', 'MVO', 'BL_ML']]
        return ready
    monkeypatch.setattr(Resolver, 'selection_ready', stale)
    response = client.post(f"/api/v1/portfolios/{p['id']}/recommendations", headers=headers(**{'If-Match': '"1"', 'Idempotency-Key': 'stale'}), json={'strategy': 'BL_ML', **({'fallback_strategy': 'EW'} if fallback else {})})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'VFF_STALE'
    assert '/private/secret' not in response.text
    if malformed:
        assert 'details' not in response.json()['error']
    else:
        assert response.json()['error']['details'] == {'asset_id': 'VFF', 'observation_date': '2026-11-03', 'age_days': 8, 'max_age_days': 7}
        assert 'tối đa 7 ngày' in response.json()['error']['message']
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0
        assert session.scalar(select(func.count()).select_from(Outbox)) == 0




def test_chat_custom_admission_uses_confirmed_version_and_cannot_supply_candidates(grants, preflight):
    client, sessions, _ = grants
    p = create(client, ['FPT', 'MWG', 'VCB', 'VFF']).json()
    grant = issue(client, p['id']).json()
    args = {'portfolio_id': p['id'], 'strategy': 'BL_ML', 'expected_version': 1, 'expected_policy_version': p['policy_version_id']}
    response = tool(client, grant, 'request_allocation', **args)
    assert response.status_code == 200, response.text
    assert tool(client, grant, 'request_allocation', **args).json() == response.json()
    assert tool(client, grant, 'request_allocation', **args, candidate_asset_ids=['GOLD']).status_code == 422
    with sessions() as session:
        job = session.get(Job, response.json()['job_id'])
        assert job.input['selection_context']['candidate_asset_ids'] == p['asset_selection']['candidate_asset_ids']
