"""Owner-scoped, append-only candidate drafts; legacy output remains unchanged."""
import pytest
from portfolio_service.models import Portfolio
from test_onboarding import answers
from test_workflow import headers, stack as workflow_stack

stack = workflow_stack


def create(client, ids, *, onboarding=True):
    body = {'name': 'Selected', 'capital_vnd': '100000000', 'asset_ids': ids}
    if onboarding:
        body['answers'] = answers()
    return client.post('/api/v1/onboarding/portfolios' if onboarding else '/api/v1/portfolios', headers=headers(), json=body)


def test_gate_default_off_and_legacy_shape_unchanged(stack, monkeypatch):
    client, _ = stack
    monkeypatch.delenv('USER_SELECTED_ASSETS_ENABLED', raising=False)
    assert create(client, ['FPT']).status_code == 403
    legacy = client.post('/api/v1/onboarding/portfolios', headers=headers(), json={'name': 'Legacy', 'capital_vnd': '100', 'answers': answers()}).json()
    assert 'asset_selection' not in legacy


def test_one_asset_and_stale_selection_save_but_do_not_submit(stack, monkeypatch):
    from portfolio_service.policy import check_candidate_feasibility
    monkeypatch.setenv('USER_SELECTED_ASSETS_ENABLED', 'true')
    client, _ = stack
    response = create(client, ['FPT'])
    assert response.status_code == 201, response.text
    p = response.json()
    assert p['universe_id'] == 'USER_SELECTED'
    assert p['asset_selection']['candidate_asset_ids'] == ['FPT']
    assert check_candidate_feasibility(['FPT'], p['constraints'], 'BL_ML') == 'INSUFFICIENT_ASSETS'
    assert p['constraints']['defensive_asset_ids'] == ['VFF']
    assert check_candidate_feasibility(['FPT', 'GOLD'], p['constraints'], 'MVO') == 'DEFENSIVE_ASSET_REQUIRED'
    assert check_candidate_feasibility(['GOLD', 'VFF'], p['constraints'], 'EW') is None
    assert check_candidate_feasibility(['FPT', 'VFF'], p['constraints'] | {'max_position_weight': .2}, 'MVO') == 'CONSTRAINTS_INFEASIBLE'


def test_revision_owner_replay_conflict_and_history_are_immutable(stack, monkeypatch):
    monkeypatch.setenv('USER_SELECTED_ASSETS_ENABLED', 'true')
    client, sessions = stack
    p = create(client, ['VFF', 'FPT']).json()
    path = f"/api/v1/portfolios/{p['id']}/asset-selections"
    before = client.get(path, headers=headers()).json()
    assert before[0]['candidate_asset_ids'] == ['FPT', 'VFF']
    intent = {'candidate_asset_ids': ['GOLD', 'VFF']}
    h = headers(**{'If-Match': '"1"', 'Idempotency-Key': 'selection-1'})
    response = client.post(path, headers=h, json=intent)
    assert response.status_code == 201, response.text
    revision = response.json()
    assert revision['portfolio_version'] == 2
    assert client.post(path, headers=h, json=intent).json() == revision
    assert client.post(path, headers=h, json={'candidate_asset_ids': ['FPT']}).status_code == 409
    assert client.post(path, headers=headers(**{'If-Match': '"1"', 'Idempotency-Key': 'selection-2'}), json=intent).status_code == 412
    for user in ['bob', 'admin']:
        assert client.get(path, headers=headers(user)).status_code == 404
        assert client.post(path, headers=headers(user, **{'If-Match': '"2"', 'Idempotency-Key': 'other'}), json=intent).status_code == 404
    after = client.get(path, headers=headers()).json()
    assert after[-1] == before[0]
    with sessions() as session:
        value = session.get(Portfolio, p['id'])
        assert value.asset_selection_revision_id == revision['revision_id']
        assert value.version == 2


@pytest.mark.parametrize('ids', [[], ['FPT', 'FPT'], ['DEMO_STOCK'], ['UNKNOWN']])
def test_bad_candidate_rejected(stack, monkeypatch, ids):
    monkeypatch.setenv('USER_SELECTED_ASSETS_ENABLED', 'true')
    client, _ = stack
    assert create(client, ids).status_code == 422


def test_creation_rejects_universe_with_assets_and_manual_draft_needs_profile(stack, monkeypatch):
    monkeypatch.setenv('USER_SELECTED_ASSETS_ENABLED', 'true')
    client, _ = stack
    response = client.post('/api/v1/onboarding/portfolios', headers=headers(), json={
        'name': 'Invalid', 'capital_vnd': '100', 'answers': answers(), 'asset_ids': ['FPT'], 'universe_id': 'DEMO'})
    assert response.status_code == 422
    p = create(client, ['GOLD', 'VFF'], onboarding=False).json()
    response = client.post(f"/api/v1/portfolios/{p['id']}/recommendations", headers=headers(**{'Idempotency-Key': 'manual', 'If-Match': '"1"'}), json={'strategy': 'EW'})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'RISK_PROFILE_REQUIRED'


def test_lightweight_policy_matches_numerical_policy():
    from portfolio_service.policy import check_candidate_feasibility, effective_constraints
    from portfolio_contracts import Constraints
    from portfolio_core.selection import check_candidate_feasibility as numerical, effective_candidate_constraints
    for ids in [['FPT'], ['FPT', 'GOLD'], ['GOLD', 'VFF'], ['FPT', 'MWG', 'VCB', 'VFF'], ['ACB', 'BID', 'CTG', 'DGC', 'FPT', 'GAS', 'VFF']]:
        for cap in [.2, .3, .5, .7]:
            for state in ['normal', 'crisis']:
                requested = Constraints(max_position_weight=cap)
                c = effective_constraints(requested, 'USER_SELECTED', state).model_dump()
                assert c == effective_candidate_constraints(requested.model_dump(), state)
                for strategy in ['EW', 'MVO', 'BL_ML']:
                    assert check_candidate_feasibility(ids, c, strategy) == numerical(ids, c, strategy)


def test_catalog_survives_missing_dependency_and_gate_off(stack, monkeypatch):
    client, _ = stack
    monkeypatch.delenv('USER_SELECTED_ASSETS_ENABLED', raising=False)
    response = client.get('/api/v1/assets/catalog', headers=headers())
    assert response.status_code == 200
    value = response.json()
    assert value['selection_enabled'] is False
    assert len(value['assets']) == 32
    assert all(item['data_status'] == 'UNKNOWN' and item['age_days'] is None for item in value['assets'])


def test_manual_fake_profile_is_not_a_saved_assessment(stack, monkeypatch):
    from uuid import uuid4
    monkeypatch.setenv('USER_SELECTED_ASSETS_ENABLED', 'true')
    client, sessions = stack
    p = create(client, ['GOLD', 'VFF'], onboarding=False).json()
    with sessions.begin() as session:
        session.get(Portfolio, p['id']).risk_profile = {'version_id': str(uuid4()), 'mapping_version': 'custom-mixed-risk-v1', 'profile': 'growth'}
    response = client.get(f"/api/v1/portfolios/{p['id']}/readiness", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()['reason_code'] == 'RISK_PROFILE_REQUIRED'
