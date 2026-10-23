"""Canonicalize isolated baseline inputs; retain raw originals in legacy_version."""
from pathlib import Path
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "trusted_baseline"
OUT = ROOT / "outputs/step1"

if __name__ == "__main__":
    canonical = OUT / "data_static/canonical_vff.csv"
    provenance = json.loads((OUT / "data_static/canonical_vff_provenance.json").read_text())
    assert hashlib.sha256(canonical.read_bytes()).hexdigest() == provenance["canonical_file_sha256"]
    assert provenance["provider_fund_id"] == 21
    frames = {
        "VFF": pd.read_csv(canonical),
        "GOLD": pd.read_csv(ROOT / "legacy_version/datasets/datasets/gold/gold_full.csv"),
    }
    changes = []
    for asset,frame in frames.items():
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame[(frame["date"] >= "2020-01-01") & (frame["date"] <= "2026-07-01")].sort_values("date")
        assert not frame["date"].duplicated().any()
        directory = "funds" if asset == "VFF" else "gold"
        for phase in ["full","train","test"]:
            selected = frame if phase == "full" else frame[frame["date"] < "2023-10-01"] if phase == "train" else frame[frame["date"] >= "2023-10-01"]
            path = BASE / "datasets" / directory / (phase if asset == "VFF" else "") / (f"VFF{'_' + phase if phase != 'full' else ''}.csv" if asset == "VFF" else f"gold_{phase}.csv")
            path.parent.mkdir(parents=True,exist_ok=True)
            selected.to_csv(path,index=False,date_format="%Y-%m-%d")
            changes.append({"asset":asset,"phase":phase,"path":str(path.relative_to(BASE)),"rows":len(selected),
                            "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                            "source":str(canonical if asset == "VFF" else ROOT / "legacy_version/datasets/datasets/gold/gold_full.csv")})
    config_path = BASE / "assets_1.json"
    config = json.loads(config_path.read_text())
    config["assets"]["GOLD"]["full_path"] = "datasets/gold/gold_full.csv"
    config_path.write_text(json.dumps(config,indent=2)+"\n")
    (OUT / "canonical_input_changes.json").write_text(json.dumps(changes,indent=2))
    print(json.dumps({"canonicalized":changes},indent=2))
