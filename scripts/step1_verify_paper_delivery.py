"""Verify the completed April-period report and its frozen research evidence."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/step1"
PAPER=OUT/"paper_period"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    active=json.loads((PAPER/"active_run.json").read_text())
    repeated=json.loads((PAPER/"reproducibility_verification.json").read_text())
    primary=OUT/"runs"/active["run_id"]
    repeat=OUT/"runs"/repeated["repeat_run_id"]
    corrected=PAPER/"corrected"
    assert active["run_id"]==repeated["primary_run_id"]
    report=(OUT/"step1_report.md").read_bytes()
    summary=(ROOT/"report.md").read_text()
    assert summary.startswith("# Step 1 — Báo cáo tóm tắt")
    assert re.findall(r"^## (\d+)\. ",summary,re.M)==[str(i) for i in range(1,5)]
    assert summary.rstrip().splitlines()[-1]=="NOT READY FOR STEP 2"
    text=report.decode()
    assert text.rstrip().splitlines()[-1]=="NOT READY FOR STEP 2"
    assert re.findall(r"^## (\d+)\. ",text,re.M)==[str(i) for i in range(1,14)]
    missing=[x for x in re.findall(r"\]\((/[^)]+)\)",text+summary) if not Path(re.sub(r":\d+$","",x)).exists()]
    assert not missing,missing
    frozen=json.loads((ROOT/"legacy_version/snapshot_manifest.json").read_text())
    for f in frozen["files"]:
        assert sha(ROOT/"legacy_version"/f["snapshot"])==f["sha256"]
        assert sha(ROOT/f["source"])==f["sha256"],f["source"]
    assert subprocess.check_output(["git","diff","--binary"],cwd=ROOT)==(OUT/"initial_tracked_diff.patch").read_bytes()
    request=json.loads((PAPER/"request.json").read_text())
    assert sha(ROOT/request["paper"])==request["paper_sha256"]
    for folder in [primary,repeat]:
        m=json.loads((folder/"manifest.json").read_text())
        assert m["status"]=="succeeded"
        assert m["config"]["TRAIN_START_DATE"]=="2020-01-01"
        assert m["config"]["SPLIT_DATE"]=="2023-10-01"
        assert m["config"]["TEST_END_DATE"]=="2026-04-30"
        assert m["aligned_inputs"]["rows"]==1573
        assert m["aligned_inputs"]["last_date"].startswith("2026-04-29")
        assert sha(folder/"runner_source.py")==m["source"]["runner_sha256"]
        for f in m["inputs"]:
            assert sha(Path(f["path"]))==f["sha256"]
        for f in m["source"]["files"]:
            assert sha(folder/"source_snapshot"/f["path"])==f["sha256"]
            if f["path"]!="STATUS.json":
                assert sha(ROOT/"trusted_baseline"/f["path"])==f["sha256"]
        for f in m["results"]["artifacts"]:
            assert sha(Path(f["path"]))==f["sha256"]
    assert repeated["status"]=="PASS" and not repeated["failures"]
    assert len(repeated["files"])==13
    for f in repeated["files"]:
        assert f["byte_identical"]
        assert sha(primary/"artifacts"/f["file"])==f["primary_sha256"]
        assert sha(repeat/"artifacts"/f["file"])==f["repeat_sha256"]
        assert sha(corrected/f["file"])==f["primary_sha256"]
    assert (primary/"ml_prediction_audit.json").read_bytes()==(repeat/"ml_prediction_audit.json").read_bytes()
    assert len(pd.read_csv(corrected/"constraint_violations.csv"))==0
    assert len(pd.read_csv(corrected/"execution_ledger.csv"))==311
    assert len(pd.read_csv(corrected/"ml_training_audit.csv"))==715
    assert len(pd.read_csv(corrected/"ml_prediction_audit.csv"))==1409
    assert len(pd.read_csv(corrected/"selection_history.csv"))==78
    assert len(list((corrected/"bl_audit_sample/corrected").glob("*.json")))==311
    metrics=pd.read_csv(corrected/"trusted_baseline_metrics.csv")
    assert set(metrics[metrics.phase=="IS"].n_returns)=={911}
    assert set(metrics[metrics.phase=="OOS"].n_returns)=={641}
    assert set(metrics[metrics.phase=="OOS"].end_date)=={"2026-04-29"}
    assert len(list((corrected/"plots").glob("*.png")))==6
    assert len(list((corrected/"plots").glob("*.pdf")))==6
    assert json.loads((PAPER/"visual_review.json").read_text())["status"]=="PASS"
    tests=(PAPER/"final_trusted_tests.log").read_text()
    assert "Ran 27 tests" in tests and tests.strip().endswith("OK")
    independent=json.loads((PAPER/"independent_review/final_run_review.json").read_text())
    assert len(independent["checks"])==52 and all(x["pass"] for x in independent["checks"].values())
    diagnostic=json.loads((PAPER/"april_run_data_diagnostics.json").read_text())
    assert all(diagnostic["checks"].values())
    assert json.loads((PAPER/"alpha_grid_method.json").read_text())["default_alpha_replay_max_nav_error"]<1e-8
    for name in ["report_review_data.json","report_review_numerical.json"]:
        reviewed=json.loads((PAPER/name).read_text())
        assert reviewed["status"]=="PASS",name
        if reviewed["report_sha256"]!=sha(OUT/"step1_report.md"):
            editorial=json.loads((PAPER/"report_wording_verification.json").read_text())
            assert editorial["status"]=="PASS"
            assert editorial["original_report_sha256"]==reviewed["report_sha256"]
            assert sha(ROOT/editorial["original_backup"])==reviewed["report_sha256"]
            assert editorial["reworded_report_sha256"]==sha(OUT/"step1_report.md")
            assert editorial["all_numeric_table_values_unchanged"]
            assert editorial["code_formula_blocks_unchanged"]
    # Prior July primary artifacts remain the same; these are deliberately not
    # relabeled as April outputs or overwritten by April diagnostics.
    july=json.loads((OUT/"reproducibility_verification.json").read_text())
    for f in july["files"]:
        assert sha(OUT/f["file"])==f["primary_sha256"]
    archive=json.loads((PAPER/"prior_july_delivery/manifest.json").read_text())
    for f in archive["files"]:
        assert sha(ROOT/f["archive"])==f["sha256"]
    status=json.loads((ROOT/"trusted_baseline/STATUS.json").read_text())
    assert status["primary_run_id"]==active["run_id"]
    assert status["strict_decision"]=="NOT READY FOR STEP 2"
    completion=json.loads((PAPER/"process_completion.json").read_text())
    assert all(x["observed_exit_code"]==0 for x in completion["runs"])
    legacy_manifest=Path(completion["runs"][-1]["manifest"])
    legacy=json.loads(legacy_manifest.read_text())
    assert legacy["status"]=="succeeded"
    legacy_folder=legacy_manifest.parent
    assert legacy["execution"]["exit_code"]==0
    assert sha(Path(legacy["source"]["runner"]))==legacy["source"]["runner_sha256"]
    for f in legacy["source"]["files"]:
        assert sha(Path(legacy["source"]["workspace"])/f["path"])==f["sha256"]
    for f in legacy["inputs"]:
        assert sha(Path(f["path"]))==f["sha256"]
    for f in legacy["results"]["artifacts"]:
        path=Path(f["path"])
        assert sha(path if path.is_absolute() else legacy_folder/path)==f["sha256"]
    assert (primary/"aligned_prices.csv").read_bytes()==(legacy_folder/"inputs/aligned_prices.csv").read_bytes()
    oldmetrics=pd.read_csv(legacy_folder/"artifacts/legacy_metrics.csv")
    assert set(oldmetrics[oldmetrics.phase=="OOS"].n_returns)=={640}
    inventory=pd.read_csv(PAPER/"deliverable_inventory.csv")
    for row in inventory.itertuples():
        if row.requested_artifact=="report.md" and sha(Path(row.absolute_path))!=row.sha256:
            assert sha(PAPER/"before_summary/report.md")==row.sha256
        elif row.requested_artifact=="step1_report.md" and sha(Path(row.absolute_path))!=row.sha256:
            assert sha(PAPER/"report_before_wording_20261006.md")==row.sha256
        else:
            assert sha(Path(row.absolute_path))==row.sha256
    for name,path in [("report.md",ROOT/"report.md"),("step1_report.md",OUT/"step1_report.md")]:
        inventory=inventory[inventory.requested_artifact!=name]
        inventory=pd.concat([inventory,pd.DataFrame([{"requested_artifact":name,"absolute_path":str(path),
            "bytes":path.stat().st_size,"sha256":sha(path),"active_period":"2020-01-01/2023-10-01/2026-04-30"}])],ignore_index=True)
    inventory.to_csv(PAPER/"deliverable_inventory.csv",index=False)
    # The previous root metadata are already preserved by the prior-delivery
    # archive. Promote pointers/inventory, while keeping July numeric CSVs.
    (OUT/"deliverable_inventory.csv").write_bytes((PAPER/"deliverable_inventory.csv").read_bytes())
    (OUT/"certification.json").write_bytes((ROOT/"trusted_baseline/STATUS.json").read_bytes())
    paths=list((ROOT/"scripts").glob("step1_*.py"))
    paths+=[ROOT/"report.md",OUT/"step1_report.md",ROOT/"trusted_baseline/README.md",ROOT/"trusted_baseline/STATUS.json",
        OUT/"change_log.md",OUT/"deliverable_inventory.csv",OUT/"certification.json",ROOT/request["paper"],primary/"manifest.json",repeat/"manifest.json",legacy_manifest]
    paths+=list(PAPER.glob("*.csv"))+list(PAPER.glob("*.json"))+list(PAPER.glob("*.md"))
    paths+=list((PAPER/"independent_review").glob("*"))+list((PAPER/"pdf_audit").glob("*.csv"))
    paths+=list(corrected.glob("*.csv"))+list((corrected/"plots").glob("*"))+[PAPER/"final_trusted_tests.log"]
    artifacts=[{"path":str(p.relative_to(ROOT)),"sha256":sha(p),"bytes":p.stat().st_size}
        for p in sorted(set(paths)) if p.is_file() and p.name!="final_delivery_verification.json"]
    result={"status":"PASS","scope":"April requested-period computation/report delivery; not unconditional Step1 research certification",
        "decision":"NOT READY FOR STEP 2","primary_run_id":active["run_id"],"repeat_run_id":repeated["repeat_run_id"],
        "identical_reports":False,"technical_report_sections":13,"summary_report_sections":4,"frozen_and_original_files_verified":len(frozen["files"]),
        "original_tracked_diff_unchanged":True,"paper_original_unchanged":True,"all_33_inputs_unchanged":True,
        "fresh_repeat_official_csv_count":13,"fresh_repeat_exact":True,"independent_actual_checks":52,
        "regression_tests_passed":27,"executions":311,"actual_training_events":715,"predictions":1409,
        "selection_events":78,"zero_substantive_constraint_violations":True,"plots_png_pdf_pairs":6,
        "prior_July_official_artifacts_preserved":True,"same_canonical_inputs_legacy_comparator":True,
        "metadata_note":"STATUS/README updated only after both April runs; original execution snapshots preserved. Numerical source/config/input unchanged.",
        "artifacts":artifacts}
    (PAPER/"final_delivery_verification.json").write_text(json.dumps(result,indent=2))
    (OUT/"final_delivery_verification.json").write_bytes((PAPER/"final_delivery_verification.json").read_bytes())
    print(json.dumps({k:v for k,v in result.items() if k!="artifacts"}))


if __name__=="__main__":
    main()
