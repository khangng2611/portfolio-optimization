from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from market_service.models import Asset, Base
from market_service.asset_metadata import MetadataProvider, sync_metadata


@pytest.fixture
def sessions():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def test_sync_persists_source_metadata_and_keeps_last_good_record_on_failure(sessions):
    class Provider:
        def fetch(self, asset):
            if asset == 'FPT':
                return {'display_name': 'FPT upstream name', 'description': 'Upstream business profile.', 'metadata_source': 'vnstock:fhsc:company.info', 'metadata_source_symbol': 'FPT'}
            raise ValueError('DESCRIPTION_UNAVAILABLE')

    results = sync_metadata(sessions, Provider(), ['FPT', 'VFF'])
    assert [row['status'] for row in results] == ['UPDATED', 'FAILED']
    with sessions() as db:
        asset = db.get(Asset, 'FPT')
        assert asset.display_name == 'FPT upstream name'
        assert asset.description == 'Upstream business profile.'
        assert asset.metadata_source == 'vnstock:fhsc:company.info'
        assert asset.metadata_fetched_at is not None
        original = asset.metadata_fetched_at
        asset.description = 'Last good description'
        db.commit()

    class Failed:
        def fetch(self, asset):
            raise OSError('secret-bearing upstream message must not be returned')

    assert sync_metadata(sessions, Failed(), ['FPT'])[0] == {'asset_id': 'FPT', 'status': 'FAILED', 'reason': 'OSError'}
    with sessions() as db:
        asset = db.get(Asset, 'FPT')
        assert asset.description == 'Last good description'
        assert asset.metadata_fetched_at == original


def test_untrusted_source_identity_and_missing_description_cannot_replace_metadata(sessions):
    class Provider:
        def fetch(self, asset):
            return {'display_name': 'Name', 'description': '', 'metadata_source': 'vnstock:fhsc:company.info', 'metadata_source_symbol': 'FPT'}

    assert sync_metadata(sessions, Provider(), ['FPT'])[0]['status'] == 'FAILED'
    with sessions() as db:
        assert db.get(Asset, 'FPT') is None
    with pytest.raises(ValueError):
        sync_metadata(sessions, Provider(), ['NOT_MODEL_SUPPORTED'])


def test_vnstock_company_profile_checks_symbol_and_strips_html():
    row = {'symbol': 'FPT', 'name': 'FPT upstream', 'profile': '<p>Technology &amp; telecom.</p><script>bad()</script>'}
    class Company:
        def info(self):
            frame = MagicMock()
            frame.__len__.return_value = 1
            frame.iloc[0].to_dict.return_value = row
            return frame

    class Reference:
        def company(self, symbol):
            return Company()

    provider = MetadataProvider(reference=Reference())
    value = provider.fetch('FPT')
    assert value['description'] == 'Technology & telecom.'
    assert value['metadata_source_symbol'] == 'FPT'
    row['symbol'] = 'MWG'
    with pytest.raises(ValueError, match='METADATA_IDENTITY_MISMATCH'):
        provider.fetch('FPT')


def test_vff_uses_verified_existing_fund_source_not_a_company_profile():
    import json

    row = {'id': 21, 'code': 'VFF', 'name': 'Upstream VFF name', 'description': 'Upstream bond fund profile', 'owner': {'shortName': 'VINACAPITAL'}, 'dataFundAssetType': {'code': 'BOND'}}

    class Mixed:
        def fetch(self, url, **kwargs):
            return json.dumps({'status': 200, 'data': {'rows': [row]}}).encode(), {}

    value = MetadataProvider(mixed=Mixed()).fetch('VFF')
    assert value['metadata_source'] == 'fmarket:vff:21'
    assert value['description'] == 'Upstream bond fund profile'
    row['code'] = 'OTHER'
    with pytest.raises(ValueError, match='identity changed'):
        MetadataProvider(mixed=Mixed()).fetch('VFF')


def test_gold_extracts_reference_text_only_after_matching_the_exact_instrument():
    from portfolio_contracts import utcnow

    today = utcnow().date()
    raw = f'''<p>Sản phẩm theo dõi: Vàng SJC 1L, 10L, 1KG · Hồ Chí Minh.</p>
    <p>Giá đóng cửa từng ngày trong tháng {today.month}/{today.year}, tính theo triệu đồng một lượng.</p>
    <table><tr><td>01/{today.month:02d}/{today.year}</td><td>120</td><td>121</td></tr></table>'''

    class Mixed:
        def fetch(self, url, **kwargs):
            return raw.encode(), {}

    value = MetadataProvider(mixed=Mixed()).fetch('GOLD')
    assert value['display_name'] == 'Vàng SJC 1L, 10L, 1KG'
    assert value['metadata_source'] == 'giavang:sjc-sell-hcm'
    assert 'một lượng' in value['description']
    raw = raw.replace('Hồ Chí Minh', 'Hà Nội')
    with pytest.raises(ValueError):
        MetadataProvider(mixed=Mixed()).fetch('GOLD')
