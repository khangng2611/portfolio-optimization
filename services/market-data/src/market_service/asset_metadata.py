"""One-shot reference sync; model eligibility and price freshness are separate concerns."""

import argparse
from html.parser import HTMLParser
import json
from zoneinfo import ZoneInfo

from portfolio_contracts import utcnow
from portfolio_contracts.assets import ASSET_IDS, canonical_candidates, supported_assets
from .models import Asset


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit * 4:
        raise ValueError('INVALID_METADATA')
    if any(ord(char) < 32 and char not in '\n\r\t' for char in value):
        raise ValueError('INVALID_METADATA')
    parser = PlainText()
    parser.feed(value)
    text = ' '.join(' '.join(parser.parts).split())
    if not text or len(text) > limit:
        raise ValueError('INVALID_METADATA')
    return text


class MetadataProvider:
    def __init__(self, reference=None, mixed=None):
        self.reference = reference
        self.mixed = mixed

    def special(self, asset):
        from .phase1_sources import MixedSource, normalize_gold_archive, verify_vff_identity

        source = self.mixed or MixedSource()
        if asset == 'VFF':
            raw, _ = source.fetch('https://api.fmarket.vn/res/products/filter', payload={
                'searchField': 'VFF', 'types': ['NEW_FUND', 'TRADING_FUND'], 'pageSize': 100,
            })
            verify_vff_identity(raw)
            row = next(row for row in json.loads(raw)['data']['rows'] if row['id'] == 21)
            return {
                'display_name': plain(row.get('name'), 500),
                'description': plain(row.get('description'), 20000),
                'metadata_source': 'fmarket:vff:21', 'metadata_source_symbol': asset,
            }
        today = utcnow().astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).date()
        raw, _ = source.fetch(f'https://giavang.tv/lich-su/{today.year}/{today.month}')
        normalize_gold_archive(raw, today.year, today.month)
        text = PlainText()
        text.feed(raw.decode('utf-8'))
        identities = [part.strip() for part in text.parts if part.strip().startswith('Sản phẩm theo dõi:')]
        explanations = [part.strip() for part in text.parts if part.strip().startswith('Giá đóng cửa từng ngày')]
        if len(identities) != 1 or len(explanations) != 1:
            raise ValueError('METADATA_IDENTITY_MISMATCH')
        identity = identities[0]
        if 'Vàng SJC 1L, 10L, 1KG' not in identity or 'Hồ Chí Minh' not in identity:
            raise ValueError('METADATA_IDENTITY_MISMATCH')
        return {
            'display_name': plain(identity.split(':', 1)[1].split(' · ')[0], 500),
            'description': plain(identity + ' ' + explanations[0], 20000),
            'metadata_source': 'giavang:sjc-sell-hcm', 'metadata_source_symbol': asset,
        }

    def fetch(self, asset):
        if asset in {'GOLD', 'VFF'}:
            # Vnstock fund/retail schemas lack a description for these exact instruments.
            return self.special(asset)
        if self.reference is None:
            from vnstock import Reference

            self.reference = Reference('fhsc')
        frame = self.reference.company(asset).info()
        if len(frame) != 1:
            raise ValueError('METADATA_IDENTITY_MISMATCH')
        row = frame.iloc[0].to_dict()
        if row.get('symbol', row.get('ticker')) != asset:
            raise ValueError('METADATA_IDENTITY_MISMATCH')
        description = row.get('profile')
        if not isinstance(description, str) or not description.strip():
            raise ValueError('DESCRIPTION_UNAVAILABLE')
        return {
            'display_name': plain(row.get('name'), 500),
            'description': plain(description, 20000),
            'metadata_source': 'vnstock:fhsc:company.info',
            'metadata_source_symbol': asset,
        }


def sync_metadata(sessions, provider, asset_ids):
    assets = canonical_candidates(asset_ids)
    registry = {asset['asset_id']: asset for asset in supported_assets()}
    results = []
    for asset_id in assets:
        try:
            value = provider.fetch(asset_id)
            name, description = plain(value['display_name'], 500), plain(value['description'], 20000)
            source = value['metadata_source']
            expected_source = {'VFF': 'fmarket:vff:21', 'GOLD': 'giavang:sjc-sell-hcm'}.get(asset_id, 'vnstock:fhsc:company.info')
            if value['metadata_source_symbol'] != asset_id or source != expected_source:
                raise ValueError('METADATA_IDENTITY_MISMATCH')
            spec = registry[asset_id]
            with sessions.begin() as session:
                asset = session.get(Asset, asset_id)
                if asset is None:
                    asset = Asset(id=asset_id, kind=spec['kind'], unit=spec['unit'])
                    session.add(asset)
                if (asset.kind, asset.unit) != (spec['kind'], spec['unit']):
                    raise ValueError('METADATA_IDENTITY_MISMATCH')
                asset.display_name, asset.description = name, description
                asset.metadata_source, asset.metadata_source_symbol = source, asset_id
                asset.metadata_fetched_at = utcnow()
            results.append({'asset_id': asset_id, 'status': 'UPDATED'})
        except Exception as exc:
            # Vendor/DB exceptions may contain credentials; emit only a bounded code.
            code = getattr(exc, 'code', None)
            reason = type(exc).__name__
            if type(exc) is ValueError and str(exc) in {
                'INVALID_METADATA', 'METADATA_IDENTITY_MISMATCH',
                'DESCRIPTION_UNAVAILABLE',
            }:
                reason = str(exc)
            elif isinstance(code, str) and code.startswith('VNSTOCK_') and len(code) <= 100:
                reason = code
            results.append({'asset_id': asset_id, 'status': 'FAILED', 'reason': reason})
    return results


def main():
    from .runtime import sessions_from_env

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-ids', nargs='+', default=list(ASSET_IDS))
    args = parser.parse_args()
    results = sync_metadata(sessions_from_env(), MetadataProvider(), args.asset_ids)
    print(json.dumps({'results': results}, ensure_ascii=False))
    raise SystemExit(1 if any(row['status'] != 'UPDATED' for row in results) else 0)


if __name__ == '__main__':
    main()
