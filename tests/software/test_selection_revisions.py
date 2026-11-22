"""Additive migration and revision CAS behavior on isolated test databases only."""
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, select
from portfolio_contracts import canonical_hash
from test_workflow import headers, stack as workflow_stack

from test_selected_portfolio import create

stack = workflow_stack


def test_selection_migration_preserves_existing_rows_and_hashes(tmp_path, monkeypatch):
    path = tmp_path / 'migration.db'
    monkeypatch.setenv('MIGRATION_DATABASE_URL', f'sqlite:///{path}')
    config = Config(str(Path('services/portfolio/alembic.ini').resolve()))
    command.upgrade(config, 'a410c7e9d201')
    engine = create_engine(f'sqlite:///{path}')
    metadata = MetaData()
    metadata.reflect(engine)
    with engine.begin() as connection:
        connection.execute(metadata.tables['app_user'].insert(), {'id': 'user', 'issuer': 'issuer', 'subject': 'alice'})
        connection.execute(metadata.tables['portfolio'].insert(), {'id': 'portfolio', 'owner_user_id': 'user', 'name': 'Legacy', 'capital_vnd': 100, 'universe_id': 'DEMO', 'constraints': {'max_position_weight': .5}, 'version': 1, 'created_at': datetime(2026, 1, 1)})
        connection.execute(metadata.tables['job'].insert(), {'id': 'job', 'owner_user_id': 'user', 'portfolio_id': 'portfolio', 'idempotency_key': 'legacy', 'body_hash': 'a' * 64, 'input_hash': 'b' * 64, 'input': {'legacy': True}, 'status': 'SUCCEEDED', 'created_at': datetime(2026, 1, 1), 'deadline': datetime(2026, 1, 1)})
        connection.execute(metadata.tables['recommendation'].insert(), {'id': 'rec', 'job_id': 'job', 'owner_user_id': 'user', 'portfolio_id': 'portfolio', 'run_id': 'run', 'result': {'weights': ['0.5', '0.5']}, 'created_at': datetime(2026, 1, 1)})
        connection.execute(metadata.tables['accepted_target'].insert(), {'id': 'target', 'recommendation_id': 'rec', 'portfolio_id': 'portfolio', 'owner_user_id': 'user', 'portfolio_version': 1, 'allocation': {'weights': ['0.5', '0.5']}, 'accepted_at': datetime(2026, 1, 1)})
    with engine.connect() as connection:
        before = {name: [dict(row) for row in connection.execute(select(metadata.tables[name])).mappings()] for name in ['portfolio', 'job', 'recommendation', 'accepted_target']}
    command.upgrade(config, 'b70211d9e301')
    updated = MetaData()
    updated.reflect(engine)
    with engine.connect() as connection:
        after = {name: [dict(row) for row in connection.execute(select(updated.tables[name])).mappings()] for name in before}
        assert after['portfolio'][0].pop('asset_selection_revision_id') is None
        assert connection.execute(select(updated.tables['portfolio_asset_selection'])).all() == []
    assert before == after
    for name, field in [('job', 'input'), ('recommendation', 'result'), ('accepted_target', 'allocation')]:
        assert canonical_hash(before[name][0][field]) == canonical_hash(after[name][0][field])


def test_selection_race_has_one_winner(stack, monkeypatch):
    monkeypatch.setenv('USER_SELECTED_ASSETS_ENABLED', 'true')
    client, _ = stack
    p = create(client, ['FPT', 'VFF']).json()
    def edit(i):
        return client.post(f"/api/v1/portfolios/{p['id']}/asset-selections", headers=headers(**{'If-Match': '"1"', 'Idempotency-Key': f'race-{i}'}), json={'candidate_asset_ids': ['GOLD', 'VFF']})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(edit, range(2)))
    assert sorted(response.status_code for response in responses) == [201, 412]
    assert len(client.get(f"/api/v1/portfolios/{p['id']}/asset-selections", headers=headers()).json()) == 2
