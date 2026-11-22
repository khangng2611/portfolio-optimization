"""Verified Phase 1 catalog; candidate order is independent of readiness."""

import hashlib
import json

EQUITY_IDS = (
    "ACB",
    "BID",
    "CTG",
    "DGC",
    "FPT",
    "GAS",
    "GVR",
    "HDB",
    "HPG",
    "LPB",
    "MBB",
    "MSN",
    "MWG",
    "PLX",
    "SAB",
    "SHB",
    "SSI",
    "STB",
    "TCB",
    "TPB",
    "VCB",
    "VHM",
    "VIB",
    "VIC",
    "VJC",
    "VNM",
    "VPB",
    "VRE",
    "BVH",
    "POW",
)
ASSET_IDS = EQUITY_IDS + ("GOLD", "VFF")

CATALOG_VERSION = "supported-assets-v1"



def canonical_candidates(ids):
    if not isinstance(ids, (list, tuple)) or not 1 <= len(ids) <= len(ASSET_IDS):
        raise ValueError("Select between 1 and 32 supported assets")
    if any(not isinstance(asset, str) or asset not in ASSET_IDS for asset in ids):
        raise ValueError("Unsupported asset")
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate candidate asset")
    return [asset for asset in ASSET_IDS if asset in ids]


def candidate_hash(ids):
    value = {
        "catalog_version": CATALOG_VERSION,
        "candidate_asset_ids": canonical_candidates(ids),
    }
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def supported_assets():
    return [
        dict(
            asset_id=asset,
            kind="stock"
            if asset in EQUITY_IDS
            else "gold"
            if asset == "GOLD"
            else "fund",
            display_name=asset,
            description=None,
            unit="VND/share"
            if asset in EQUITY_IDS
            else "VND/tael"
            if asset == "GOLD"
            else "VND/unit",
            currency="VND",
            catalog_version=CATALOG_VERSION,
        )
        for asset in ASSET_IDS
    ]
