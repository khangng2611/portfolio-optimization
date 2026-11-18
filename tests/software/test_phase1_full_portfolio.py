"""Full-universe policy and independently checked accepted-job pins."""
import copy

import pytest
from portfolio_contracts import Constraints
from portfolio_service.policy import effective_constraints
from portfolio_service.workflow import validate_result
from test_workflow import stack as workflow_stack

stack = workflow_stack


def test_full_policy_preserves_stricter_profile_and_uses_crisis_floor():
    requested = Constraints(risk_aversion=3, max_position_weight=.4,
                            min_defensive_weight=.4, max_non_defensive_weight=.6)
    actual = effective_constraints(requested, 'VN_PHASE1_FULL', 'crisis')
    assert actual.risk_aversion == 5
    assert actual.max_position_weight == .4
    assert actual.defensive_asset_ids == ['VFF']
    assert actual.min_defensive_weight == .4
    assert actual.max_non_defensive_weight == .6
    assert requested.defensive_asset_ids == []
    assert effective_constraints(requested, 'DEMO', 'crisis') == requested


def fixture():
    active = ['A', 'B', 'C', 'D', 'E', 'GOLD', 'VFF']
    phase = {'active_asset_ids': active, 'selected_equity_ids': active[:5],
             'selection_id': 'a' * 64, 'selection_epoch': '2026-11-01',
             'fit_epoch': '2026-11-02'}
    command = {'inputs': {'asset_ids': active + ['INACTIVE'], 'model_bundle_id': 'model-1',
                          'provenance': {'phase1_full': phase}},
               'constraints': effective_constraints(Constraints(), 'VN_PHASE1_FULL').model_dump(),
               'strategy': 'BL_ML', 'core_version': '0.1.0'}
    inference = {key: phase[key] for key in ('active_asset_ids', 'selection_id', 'selection_epoch', 'fit_epoch')}
    inference['model_manifest_hash'] = 'model-1'
    result = {'asset_ids': command['inputs']['asset_ids'], 'weights': [.1] * 5 + [.2, .3, 0],
              'strategy': 'BL_ML', 'core_version': '0.1.0', 'status': 'optimal',
              'diagnostics': {'inference': inference}}
    return command, result


def test_full_result_checks_inactive_weights_and_selection_model_pins():
    command, result = fixture()
    validate_result(result, command)
    bad = copy.deepcopy(result)
    bad['weights'][0] -= .01
    bad['weights'][-1] = .01
    with pytest.raises(ValueError, match='Inactive'):
        validate_result(bad, command)
    bad = copy.deepcopy(result)
    bad['diagnostics']['inference'] = ['invalid']
    with pytest.raises(ValueError, match='inference'):
        validate_result(bad, command)
    for field in ('selection_id', 'selection_epoch', 'fit_epoch', 'model_manifest_hash', 'active_asset_ids'):
        bad = copy.deepcopy(result)
        bad['diagnostics']['inference'][field] = 'wrong'
        with pytest.raises(ValueError, match='inference'):
            validate_result(bad, command)


def test_full_onboarding_and_reassessment_keep_defensive_policy(stack):
    from test_onboarding import answers
    from test_workflow import headers
    client, _ = stack
    response = client.post('/api/v1/onboarding/portfolios', headers=headers(), json={
        'name': 'Full', 'capital_vnd': '100000000', 'universe_id': 'VN_PHASE1_FULL',
        'answers': answers(),
    })
    assert response.status_code == 201, response.text
    portfolio = response.json()
    pid = portfolio['id']
    expected = {'defensive_asset_ids': ['VFF'], 'min_defensive_weight': .15,
                'max_non_defensive_weight': .7}
    for key, value in expected.items():
        assert portfolio['constraints'][key] == value
    history = client.get(f'/api/v1/portfolios/{pid}/risk-assessments', headers=headers()).json()
    preview = client.post(f'/api/v1/portfolios/{pid}/risk-assessments/preview', headers=headers(),
                          json={'answers': answers(horizon_months=6)}).json()
    assert preview['after']['constraints']['defensive_asset_ids'] == ['VFF']
    confirm = client.post(f'/api/v1/portfolios/{pid}/risk-assessments', headers=headers(**{
        'If-Match': '\"1\"', 'Idempotency-Key': 'full-risk'}),
        json={'answers': answers(horizon_months=6)})
    assert confirm.status_code == 201, confirm.text
    for key, value in expected.items():
        assert confirm.json()['constraints'][key] == value
    later = client.get(f'/api/v1/portfolios/{pid}/risk-assessments', headers=headers()).json()
    assert later[-1] == history[0] | {'is_active': False}




def test_job_freezes_crisis_policy_and_provenance_then_persists_receipt(stack, monkeypatch):
    import json
    from pathlib import Path
    from uuid import uuid4
    from portfolio_contracts import Envelope, OptimizeCommand, OptimizeResult
    from portfolio_service.models import Job, Portfolio
    from portfolio_service.workflow import consume_result
    from test_onboarding import answers
    from test_workflow import Resolver, headers

    original = Resolver.ready
    ids = json.loads(Path('assets_1.json').read_text())['default_selection']
    active = ids[:5] + ['GOLD', 'VFF']
    phase = {'active_asset_ids': active, 'selected_equity_ids': ids[:5],
             'selection_id': 'a' * 64, 'selection_epoch': '2026-11-01',
             'fit_epoch': '2026-11-02', 'regime': {'regime': 'crisis'}}
    def ready(self, universe_id, strategy):
        return original(self, universe_id, strategy) | {
            'asset_ids': ids, 'model_bundle_id': 'b' * 64,
            'provenance': {'data_origin': 'real', 'phase1_full': phase}, 'demo': False,
        }
    monkeypatch.setattr(Resolver, 'ready', ready)
    client, sessions = stack
    p = client.post('/api/v1/onboarding/portfolios', headers=headers(), json={
        'name': 'Full', 'capital_vnd': '100000000', 'universe_id': 'VN_PHASE1_FULL',
        'answers': answers(),
    }).json()
    path = f"/api/v1/portfolios/{p['id']}/recommendations"
    kwargs = {'headers': headers(**{'Idempotency-Key': 'full-job'}), 'json': {'strategy': 'BL_ML'}}
    accepted = client.post(path, **kwargs)
    assert accepted.status_code == 202, accepted.text
    jid = accepted.json()['job_id']
    assert client.post(path, **kwargs).json() == accepted.json()
    assert client.post(path, headers=headers('bob', **{'Idempotency-Key': 'other'}), json={'strategy': 'BL_ML'}).status_code == 404
    with sessions() as session:
        job = session.get(Job, jid)
        command = copy.deepcopy(job.input)
        assert command['constraints']['risk_aversion'] == 5
        assert command['decision_context']['requested_constraints']['risk_aversion'] == 3
        assert session.get(Portfolio, p['id']).constraints['risk_aversion'] == 3
        assert OptimizeCommand.model_validate(command).compute_hash() == job.input_hash
    inference = {key: phase[key] for key in ('active_asset_ids', 'selection_id', 'selection_epoch', 'fit_epoch')}
    inference['model_manifest_hash'] = 'b' * 64
    weights = [.1 if a in ids[:5] else .2 if a == 'GOLD' else .3 if a == 'VFF' else 0 for a in ids]
    payload = OptimizeResult(job_id=jid, input_hash=command['input_hash'], run_id=uuid4(), bundle_hash='a' * 64, status='SUCCEEDED', result={
        'strategy': 'BL_ML', 'asset_ids': ids, 'weights': weights, 'status': 'optimal',
        'core_version': '0.1.0', 'diagnostics': {'inference': inference},
    })
    consume_result(sessions, Envelope(type='quant.optimization.completed', producer='quant-serving', correlation_id=jid, payload=payload.model_dump(mode='json')))
    result = client.get(f'/api/v1/recommendations/{jid}', headers=headers()).json()
    assert result['constraints']['risk_aversion'] == 5
    assert result['requested_constraints']['risk_aversion'] == 3
    assert result['inputs_provenance']['phase1_full'] == phase
    phase['selection_id'] = 'c' * 64
    with sessions() as session:
        assert session.get(Job, jid).input == command

    changed = client.patch(f"/api/v1/portfolios/{p['id']}", headers=headers(**{'If-Match': '"1"'}), json={'max_position_weight': .2})
    assert changed.status_code == 200
    infeasible = client.post(path, headers=headers(**{'Idempotency-Key': 'infeasible'}), json={'strategy': 'BL_ML'})
    assert infeasible.status_code == 409


@pytest.mark.parametrize('malformed', [None, 'asset_id', 'age_days', 'max_age_days', 'observation_date'])
@pytest.mark.parametrize('asset', ['VFF', 'GOLD'])
@pytest.mark.parametrize('fallback', [None, 'EW'])
def test_quant_stale_reason_reaches_api_without_job_or_fallback(stack, monkeypatch, asset, fallback, malformed):
    import time
    import httpx
    from sqlalchemy import func, select
    from portfolio_service.models import Job, Outbox
    from portfolio_service.runtime import QuantResolver
    from test_workflow import Resolver, headers, portfolio
    client, sessions = stack
    pid = portfolio(client)
    detail = {'code': f'{asset}_STALE', 'message': f'{asset} eligible observation is 8 days old; freshness maximum is 7 days',
              'details': {'asset_id': asset, 'observation_date': '2026-11-03', 'age_days': 8, 'max_age_days': 7}}
    if malformed:
        detail['details'][malformed] = {'asset_id': 'OTHER', 'age_days': True, 'max_age_days': 8, 'observation_date': 'invalid'}[malformed]
        detail['message'] = 'private upstream diagnostics'
    calls = []
    def respond(url, **kwargs):
        calls.append(kwargs['params']['strategy'])
        return httpx.Response(409, json={'detail': detail}, request=httpx.Request('GET', url))
    monkeypatch.setenv('QUANT_API_URL', 'http://quant')
    monkeypatch.setattr('portfolio_service.runtime.httpx.get', respond)
    resolver = QuantResolver()
    resolver.token, resolver.expires = 'test-token', time.monotonic() + 60
    monkeypatch.setattr(Resolver, 'ready', lambda self, universe, strategy: resolver.ready(universe, strategy))
    body = {'strategy': 'BL_ML'}
    if fallback:
        body['fallback_strategy'] = fallback
    response = client.post(f'/api/v1/portfolios/{pid}/recommendations', headers=headers(**{'Idempotency-Key': 'stale'}), json=body)
    assert response.status_code == (503 if malformed else 409), response.text
    if malformed:
        assert response.json()['error']['code'] == 'DEPENDENCY_UNAVAILABLE'
        assert 'private upstream diagnostics' not in response.text
    else:
        assert response.json()['error'] == detail | {'retryable': False}
    assert calls == ['BL_ML']
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0
        assert session.scalar(select(func.count()).select_from(Outbox)) == 0
