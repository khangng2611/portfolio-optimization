"""Validate the final Step 1 delivery without running a strategy or changing inputs."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/step1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    report=(ROOT/"report.md").read_bytes()
    assert report==(OUT/"step1_report.md").read_bytes()
    text=report.decode()
    assert text.rstrip().splitlines()[-1]=="NOT READY FOR STEP 2"
    sections=re.findall(r"^## (\d+)\. ",text,re.M)
    assert sections==[str(i) for i in range(1,14)],sections
    missing_links=[]
    for target in re.findall(r"\]\((/[^)]+)\)",text):
        if not Path(target).exists():missing_links.append(target)
    assert not missing_links,missing_links
    frozen=json.loads((ROOT/"legacy_version/snapshot_manifest.json").read_text())
    for f in frozen["files"]:
        assert sha(ROOT/"legacy_version"/f["snapshot"])==f["sha256"]
        assert (ROOT/f["source"]).is_file(),f["source"]
        assert sha(ROOT/f["source"])==f["sha256"],f["source"]
    current_diff=subprocess.check_output(["git","diff","--binary"],cwd=ROOT)
    assert current_diff==(OUT/"initial_tracked_diff.patch").read_bytes()

    primary=OUT/"runs/corrected-20261004T085654"
    repeat=OUT/"runs/corrected-20261004T090341"
    manifests=[]
    for folder in [primary,repeat]:
        manifest=json.loads((folder/"manifest.json").read_text())
        assert manifest["status"]=="succeeded"
        for f in manifest["inputs"]:
            assert sha(Path(f["path"]))==f["sha256"]
        for f in manifest["source"]["files"]:
            path=ROOT/"trusted_baseline"/f["path"]
            if f["path"]=="STATUS.json":
                path=OUT/"source_metadata_at_execution/STATUS.json"
            assert sha(path)==f["sha256"],f["path"]
        manifests.append(folder/"manifest.json")
    repeated=json.loads((OUT/"reproducibility_verification.json").read_text())
    assert repeated["status"]=="PASS" and all(x["byte_identical"] for x in repeated["files"])
    for f in repeated["files"]:
        assert sha(OUT/f["file"])==f["primary_sha256"]
        assert sha(repeat/"artifacts"/f["file"])==f["repeat_sha256"]
    assert len(pd.read_csv(OUT/"constraint_violations.csv"))==0
    assert len(pd.read_csv(OUT/"execution_ledger.csv"))==319
    assert len(pd.read_csv(OUT/"ml_training_audit.csv"))==735
    assert len(pd.read_csv(OUT/"selection_history.csv"))==80
    assert len(list((OUT/"bl_audit_sample/corrected").glob("*.json")))==319
    assert len(list((OUT/"plots").glob("*.png")))==6
    assert len(list((OUT/"plots").glob("*.pdf")))==6
    tests=(OUT/"final_trusted_tests.log").read_text()
    assert "Ran 27 tests" in tests and tests.strip().endswith("OK")
    assert json.loads((ROOT/"trusted_baseline/STATUS.json").read_text())["strict_decision"]=="NOT READY FOR STEP 2"

    inventory=pd.read_csv(OUT/"deliverable_inventory.csv")
    extra=[]
    for name,path in [("report.md",ROOT/"report.md"),("step1_report.md",OUT/"step1_report.md")]:
        extra.append({"requested_artifact":name,"absolute_path":str(path),"bytes":path.stat().st_size,
                      "sha256":sha(path),"status":"created"})
    inventory=inventory[~inventory.requested_artifact.isin(["report.md","step1_report.md"])]
    pd.concat([inventory,pd.DataFrame(extra)],ignore_index=True).to_csv(OUT/"deliverable_inventory.csv",index=False)
    artifacts=[]
    paths=list((ROOT/"scripts").glob("step1_*.py"))+[ROOT/"report.md"]+manifests
    paths+=list((OUT/"plots").glob("*"))
    paths+=list(OUT.glob("*.csv"))+list(OUT.glob("*.json"))+list(OUT.glob("*.md"))
    paths+=[ROOT/"trusted_baseline/README.md",ROOT/"trusted_baseline/STATUS.json",OUT/"final_trusted_tests.log"]
    for folder in ["ml_static","data_static","portfolio_static"]:
        paths+=list((OUT/folder).glob("final_run_review.*"))
    for path in sorted(set(paths)):
        if path.is_file() and path.name!="final_delivery_verification.json":
            artifacts.append({"path":str(path.relative_to(ROOT)),"sha256":sha(path),"bytes":path.stat().st_size})
    result={"status":"PASS","decision":"NOT READY FOR STEP 2",
        "identical_reports":True,"required_sections":13,"required_deliverables_present":True,
        "frozen_and_original_files_verified":len(frozen["files"]),"original_tracked_diff_unchanged":True,
        "fresh_run_outputs_still_identical":True,"actual_model_events":735,"execution_events":319,
        "zero_substantive_constraint_violations":True,"regression_tests":27,"plots_png_pdf_pairs":6,
        "controlled_metadata_change":"Post-run STATUS.json updated; creation-time metadata hash verified from source_metadata_at_execution/STATUS.json. No numerical source/config/input changed.",
        "artifacts":artifacts}
    (OUT/"final_delivery_verification.json").write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!="artifacts"}))


if __name__=="__main__":
    main()
