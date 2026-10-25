# Core Evidence Sprint

This package implements the next research work requested in guide_1.md/project_1.md. The report is `docs/core_experiment_report.md`. Local numerical results are exposed through `outputs/`, pointing to the primary immutable run outputs.

Run from the portfolio-optimization repository root with the established research interpreter:

```sh
venv/bin/python -B -m unittest discover -s experiments_core/tests -v
venv/bin/python -B -m experiments_core.src.run
venv/bin/python -B -m experiments_core.src.run --parent-run RUN_ID
venv/bin/python -B -m experiments_core.src.validate RUN_ID REPEAT_ID
venv/bin/python -B -m experiments_core.src.report RUN_ID REPEAT_ID
```

The runner only imports numerical functions from `outputs/step1/readiness_20261012/candidate_workspace`, not current application modules or current root datasets. Data, source, policy, saved causal selections/views, environment and seeds are identified by hashes before execution. No model refit, parameter search, data download or modification of Step1 is performed.

Primary run: `core-evidence-20261023T211011`; repeat: `core-evidence-20261023T211139`. Saved signals are reused; no pretrained model-cache inference is used. A3 and B1 deliberately specify the same prior-only allocation and provide an independently solved identity gate. Optional confidence/regime/Hybrid probes are not run.

The submission evidence ZIP preserves this package, both run records and all frozen baseline inputs required by its verification path, including baseline source_snapshot and the inherited fresh-fit repeat CSVs. Extract it into a checkout of the source commit recorded in the manifest to preserve Git provenance. The research environment is not vendored; installed versions are recorded in each run's requirements_frozen.txt. Existing `venv/` is reused and kept separate from `.venv-software`.

Word production uses bundled Codex artifact dependencies, not the research interpreter. See `src/build_docx.py`; render and sanitize using the Documents skill. Rendered PNGs are QA intermediates. The report and archive are submitted to the folder explicitly designated by the user; no sharing permissions or messages to the supervisor are changed.
