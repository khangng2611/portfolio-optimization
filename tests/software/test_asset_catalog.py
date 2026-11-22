import pytest
from portfolio_core.assets import canonical_candidates, candidate_hash, supported_assets
from quant_service.asset_catalog import asset_catalog


def test_candidate_hash_is_canonical():
    assert canonical_candidates(["VFF", "FPT", "MWG"]) == ["FPT", "MWG", "VFF"]
    assert candidate_hash(["VFF", "FPT"]) == candidate_hash(["FPT", "VFF"])
    for ids in ([], ["FPT", "FPT"], ["DEMO"], ["fpt"], ["VNINDEX"]):
        with pytest.raises(ValueError):
            canonical_candidates(ids)


def test_catalog_survives_missing_expired_and_stale_bundles():
    assets = supported_assets()
    assert len(assets) == 32
    assert assets[-1]["kind"] == "fund"
    assert assets[-2]["unit"] == "VND/tael"
    for unavailable in (None, object()):
        result = asset_catalog(unavailable)
        assert len(result["assets"]) == 32
        assert all(a["data_status"] == "UNKNOWN" for a in result["assets"])
        assert all(a["available_at"] is None for a in result["assets"])
        assert result["catalog_version"] == "supported-assets-v1"


def test_model_catalog_contains_only_structural_identity_not_issuer_metadata():
    assets = {asset["asset_id"]: asset for asset in asset_catalog()["assets"]}
    assert len(assets) == 32
    assert all(asset['display_name'] == asset_id and asset['description'] is None for asset_id, asset in assets.items())


def test_older_catalog_items_can_omit_description():
    from portfolio_contracts.selection import AssetCatalogItem

    item = supported_assets()[0].copy()
    item.pop("description", None)
    assert AssetCatalogItem(**item).description is None
