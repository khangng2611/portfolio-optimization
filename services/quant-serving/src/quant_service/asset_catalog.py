"""Catalog visibility never depends on publication availability."""

import os

from portfolio_contracts.selection import AssetCatalogItem
from portfolio_core.assets import CATALOG_VERSION, supported_assets


def asset_catalog(catalog=None):
    assets = [
        AssetCatalogItem(**asset).model_dump(mode="json")
        for asset in supported_assets()
    ]
    if catalog is not None and hasattr(catalog, "selection_catalog"):
        try:
            statuses = catalog.selection_catalog.asset_status()
        except (ValueError, OSError, KeyError, TypeError):
            statuses = {}
        for asset in assets:
            if asset["asset_id"] in statuses:
                asset.update(statuses[asset["asset_id"]])
    return dict(
        catalog_version=CATALOG_VERSION,
        selection_enabled=os.getenv("USER_SELECTED_ASSETS_ENABLED", "false").lower()
        == "true",
        assets=assets,
    )
