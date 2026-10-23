# Step 1 candidate baseline

This isolated research copy contains integrity corrections and verified computations for the user's requested paper period **2020-01-01 to 2026-04-30**, split **2023-10-01**. The last observed session is **2026-04-29**. Prior July-period results are preserved. The original project code/data and `legacy_version/` remain unchanged.

**Strict research certification: NOT READY FOR STEP 2.** Numerical timing, actual training-label windows, final target constraints, fixed-share NAV/turnover, BL arithmetic and fresh-run determinism pass. Historical VFF/GOLD public release/revision availability, GOLD quote metadata and stock corporate-action/return definitions remain unverified. The historical manuscript was reconciled by archived-decision replay rather than an independent complete refit in its unknown original environment.

Read the concise results/current-status summary at `../report.md`. The full technical report with the13 sections required by the lecturer remains at `../outputs/step1/step1_report.md`; final metadata are in `STATUS.json`. Required `trusted_baseline_*` filenames describe the requested export layout, not an unconditional certification.

## Reproduce the frozen computation

From the original project root:

```sh
MPLCONFIGDIR=/private/tmp/portfolio-step1-mpl XDG_CACHE_HOME=/private/tmp/portfolio-step1-cache venv/bin/python scripts/step1_run_baseline.py --verification-run --run-label paper-period --start-date 2020-01-01 --split-date 2023-10-01 --end-date 2026-04-30
```

This uses this directory's code, canonical full input files and frozen scientific parameters. It fits new models and creates a timestamped run under `outputs/step1/runs/`, with separate artifacts and manifest; it does not overwrite primary results when `--verification-run` is provided. No model cache is reused. Use the existing `venv/bin/python`, not the software-service environment. Do not recrawl inputs while reproducing this snapshot.

Active primary: `corrected-paper-period-20261004T132742`. Fresh repeat: `corrected-paper-period-repeat-20261004T133908`. Both use end inclusive April30 and produce byte-identical13CSV, actual predictions and training audits. Active exports are in `../outputs/step1/paper_period/corrected/`, and `paper_period/active_run.json` points to the run. Each run's `run_config.json`, seeds, environment, manifest, captured runner and source snapshot are authoritative. On-disk `config.py` and root generated config retain the previous July default; explicitly pass the April CLI flags above. Scientific parameters and input snapshots were not changed by this date rerun.

Prior July runs `corrected-20261004T085654` and `corrected-20261004T090341`, root output CSVs and old report snapshots under `paper_period/prior_july_delivery/` remain available. The April actual review also confirms exact agreement with July's common causal prefix. The controlled legacy comparator in `paper_period/legacy_on_canonical_inputs/` uses the same canonical matrix but preserves original logic; it is not an exact historical input recreation of the manuscript.

From this directory, run regressions with:

```sh
MPLCONFIGDIR=/private/tmp/portfolio-step1-mpl XDG_CACHE_HOME=/private/tmp/portfolio-step1-cache ../venv/bin/python -B -m unittest discover -s tests -v
```

Final verified result: 27 tests passed. The new `outputs/step1/paper_period/final_trusted_tests.log` records that result; independent actual review52checks and repeat40checks also pass. Running discovery from the original project root without explicitly selecting this copy can import legacy modules; use the command above.

## Conventions kept for later experiments

- Static 30-stock universe plus GOLD/VFF, representative K5.
- Expanding correlation history; covariance20 sessions; rebalance/retrain/reselect5/10/20.
- Features retain one-price-row lag; internal fitting labels are purged before validation. Model hyperparameters and seeds remain legacy.
- Decision after close(t), execute at next observed session close(t+1), target earns its first return ending(t+2).
- Fixed asset units between trades; turnover uses drifted pretrade weights.
- GOLD is non-defensive in existing group constraints. BL non-defensive cap0.70 implies VFF floor0.30 even though the separate nominal floor is0.15.
- Hybrid blends full32 MVO with active7 BL and does not inherit BL group caps. Normal/stress/crisis alphas0.6/0.3/0.1 remain unchanged.
- Prices are frictionless valuation proxies. VFF dealing/settlement and GOLD quote sides are not validated executable fills. Historical information is aligned by valuation date under an explicit unresolved availability assumption.
- Zero transaction costs, no new strategies or performance tuning. Point-in-time membership, matched-constraint/no-ML ablations and cost sensitivity remain later steps.

Do not use the preserved crawler/other non-default experimental modes to refresh this baseline or infer they were audited to the same extent as the default `ranking_absolute` run. The detailed change log is `../outputs/step1/change_log.md`.
