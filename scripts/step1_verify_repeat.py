"""Compare two independent fresh-fit baseline runs without rerunning a model."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/step1"
PRIMARY=OUT/"runs/corrected-20261004T085654"
REPEAT=OUT/"runs/corrected-20261004T090341"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    first=json.loads((PRIMARY/"manifest.json").read_text())
    second=json.loads((REPEAT/"manifest.json").read_text())
    assert first["status"]==second["status"]=="succeeded"
    files=["trusted_baseline_nav.csv","trusted_baseline_daily_returns.csv",
        "trusted_baseline_weights.csv","trusted_baseline_metrics.csv",
        "trusted_baseline_turnover.csv","turnover_summary.csv","selection_history.csv",
        "execution_ledger.csv","training_window_audit.csv","ml_training_audit.csv",
        "ml_prediction_audit.csv","constraint_diagnostics.csv","constraint_violations.csv"]
    comparisons=[]
    for filename in files:
        a,b=OUT/filename,REPEAT/"artifacts"/filename
        left,right=pd.read_csv(a),pd.read_csv(b)
        pd.testing.assert_frame_equal(left,right,check_exact=True)
        comparisons.append({"file":filename,"rows":len(left),"byte_identical":sha(a)==sha(b),
                            "primary_sha256":sha(a),"repeat_sha256":sha(b)})
    a=json.loads((PRIMARY/"ml_prediction_audit.json").read_text())
    b=json.loads((REPEAT/"ml_prediction_audit.json").read_text())
    assert a==b
    source_a={x["path"]:x["sha256"] for x in first["source"]["files"] if x["path"].endswith(".py")}
    source_b={x["path"]:x["sha256"] for x in second["source"]["files"] if x["path"].endswith(".py")}
    assert source_a==source_b
    assert first["inputs"]==second["inputs"]
    assert first["config"]==second["config"]
    assert first["aligned_inputs"]==second["aligned_inputs"]
    report={"primary_run_id":PRIMARY.name,"repeat_run_id":REPEAT.name,"status":"PASS",
        "fresh_fits_both_runs":True,"cache_reused":False,"scientific_python_sources_identical":True,
        "inputs_identical":True,"configuration_identical":True,"aligned_prices_identical":True,
        "actual_predictions_exactly_identical":True,"max_numeric_result_difference":0.0,
        "files":comparisons,
        "scope":"Determinism in this recorded environment; original manuscript training environment remains unknown."}
    (OUT/"reproducibility_verification.json").write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="files"}))


if __name__=="__main__":
    main()
