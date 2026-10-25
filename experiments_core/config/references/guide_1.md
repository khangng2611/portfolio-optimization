# guide_0.md — STEP 1: Core Evidence Sprint (5–7 Working Days)

**Version:** 2026-10-14 — revised instructions for the student  
**Depends on:** new `project_0.md`, *Báo cáo Step 1* updated 12/10/2026.  
**Purpose:** Generate the **minimum rigorous incremental evidence** needed to revise the existing portfolio-optimization paper. **Do not rerun the former 26-section integrity Step 1 from scratch.**

> **Time box:** finish the *experimental work* within **D1–D5**, using **D6–D7 only for QA, reruns of failed mandatory checks, figures and reporting**. Start writing in parallel. Use existing frozen code, data and saved signals wherever scientifically valid.

## 0. Completion contract — read before coding

### Deliverables we must have by D7

1. **A: asset selection comparison** — `Full 30`, `Random K=5` (10 predetermined seeds), `Simple K=5`, `Proposed K=5` with **one fixed downstream model**, both structural and portfolio comparisons.
2. **B: matched optimization ladder** — `MVO matched`, `BL-no-ML`, `BL+ML` using the **same Proposed 5 + GOLD + VFF** and **same feasible set**; legacy Hybrid is a **descriptive reference only**.
3. **Cost sensitivity** on available trade records (0/10/25/50 bps) and **paired block-bootstrap** intervals for primary comparisons.
4. **Full audit trail:** frozen inputs/config/seed hashes; no leakage; constraint, compounding, unit and metric consistency; raw returns/weights and reproducible tables.
5. **`core_experiment_report.md`** with direct hypothesis-by-hypothesis conclusions and limitations, without tuning OOS or overclaiming.

**Optional only if already config-driven:** fixed vs dynamic confidence; regime defense on/off; matched hybrid. Optional probes never delay mandatory A/B. Full PIT VN30, fully verified vintage prices, real fund execution and new algorithms are **out of scope**.

### Pre-committed rules

- **Information contract:** use frozen 12/10 policy throughout, not actual quote-date as a decision-information timestamp. Decision cutoff 18:00 VN; VFF information available only after five observed VNINDEX sessions or later recorded source timestamp; GOLD dated D information from D+1; use `available_at <= decision_cutoff` for input streams. Keep valuation series separate.
- **Temporal execution:** decision after close(t), execute close(t+1), new holding first earns t+1→t+2. Never earn an already observed return.
- **Data:** static 30-stock universe (a fixed proxy, *not* point-in-time VN30), GOLD/VFF valuation proxies, KBS adjusted-close as in source baseline. No replacement dataset unless critical correctness problem found and explicitly logged.
- **Parameter freeze:** No K tuning (`K=5`), no retrain/hyperparameter/regime/alpha optimization driven by OOS. Fixed costs, block lengths and random seeds **before** assessing OOS results.
- **Metric basis:** common OOS **641 return dates** from 02/10/2023–29/04/2026, NAV anchor 29/09/2023, no future returns after sample end. Use existing annualization, 6%-per-year risk-free Sharpe convention and turnover definition consistently.
- **Attribution:** separate historical *unmatched* EW/MVO/BL+ML/Hybrid from new **matched** comparisons. A difference in Sharpe alone without uncertainty does not prove superiority.

## 1. D1: Freeze active baseline and make a small experiment runner

### 1.1 Verify the correct snapshot, NOT the old logs

Use existing artifacts associated with:

```text
baseline_run_id = availability-observed-contract-20261012T233110
baseline_source = readiness_20261012/candidate_workspace/
```

Verify the following reported OOS numbers to displayed precision:

| Strategy | NAV | Sharpe | MDD | Annual turnover |
|---|---:|---:|---:|---:|
| EW | 1.7278 | 0.946 | -17.08% | 0.628 |
| MVO | 3.3904 | 1.441 | -30.18% | 23.363 |
| BL+ML | 1.8136 | 1.385 | -9.51% | 8.200 |
| Hybrid | 2.7044 | 1.665 | -16.13% | 16.613 |

If the reference is not reproducible, STOP creating new paper tables. Record exact missing inputs/version and fix only that blocking inconsistency; do not silently substitute the 04/10 baseline.

Keep `legacy_version/` and the 12/10 baseline immutable. New code goes only under `experiments_core/`.

### 1.2 Output structure

```text
experiments_core/
  config/
    frozen_baseline_ref.json
    experiment_plan.json
    seeds.json
  src/
  runs/
  outputs/
    experiment_registry.csv
    baseline_reproduction.md
    selection_structure.csv
    selection_history_comparison.csv
    selection_portfolio_metrics.csv
    selection_portfolio_returns.csv
    selection_portfolio_weights.csv
    optimizer_ladder_metrics.csv
    ablation_daily_returns.csv
    ablation_weights.csv
    cost_sensitivity.csv
    uncertainty_intervals.csv
    mechanism_probes.csv              # only if run
    plots/
  docs/
    deviations.md
    matched_constraints.md
    core_experiment_report.md
```

Add to each `experiment_registry.csv` row: `experiment_id, hypothesis, selection_method, universe, optimizer, ML_view, confidence, regime, constraints_hash, data_hash, seed, IS_start, IS_end, OOS_start, OOS_end, run_status, metrics_path, code_commit, runtime_minutes`.

### 1.3 Define a single reusable runner

```python
run_experiment(
    selection_method,
    optimizer,
    ml_views,
    confidence_mode,
    regime_mode,
    seed,
    frozen_inputs,
    constraints_config,
)
```

This is pseudocode, not a requirement to rewrite the project architecture. A configuration wrapper around the existing runner is sufficient. Save all portfolio daily returns, weights, event-level turnover and run metadata, not metrics alone.

**D1 acceptance gate:** baseline reproduced; config/hash/cutoff frozen; matched constraints declared; all additional parameters and seeds fixed **before looking at ablation OOS metrics**. If needed, use one small IS smoke test to check the runner.

## 2. D2–D3: Experiment A — Do representative stocks really help?

### 2.1 Research question and single-variable control

> Keeping the downstream **BL-prior/no-ML portfolio construction** fixed, does proposed correlation-coverage selection preserve diversification and improve portfolio results versus Random/Simple K=5?

**Why use BL-prior/no-ML here:** avoiding additional ML retraining for different selections reduces computational cost and prevents ML interaction from obscuring the selection effect. This is a **new controlled ablation**, not a recreation of legacy BL+ML.

Freeze the same historical close/availability/covariance/selection calendars and asset-group constraints. Keep defensive assets **GOLD + VFF** in all arms. No confidence, regime views, hybrid or alpha. No costs for gross A metrics. BL prior `pi=delta*Sigma*w_eq` with the same `delta, tau`, covariance lookback, optimization objective/risk aversion, constraints, and `w_eq` rule throughout. **If no views, the posterior is the prior**; do not substitute the legacy no-view sample-mean fallback.

### 2.2 Four selection arms

| Arm | Equity members at each reselection | Rule and information timing |
|---|---|---|
| **A0 Full 30** | All 30 equities | Same frozen static equity universe; reference for dimensionality effect |
| **A1 Random K5** | 5 of 30 | Sample without replacement at each *same* 20-session selection date; repeat with 10 fixed seeds |
| **A2 Simple K5** | 5 of 30 | Select stocks with **lowest 20-session realized volatility** ending no later than `t−1`, stable ticker tie-break |
| **A3 Proposed K5** | 5 of 30 | Current exact correlation-coverage exhaustive selection (`sum_i min_m(1−rho[i,m])`); history to `t−1` |

**Why this Simple benchmark:** same stored adjusted-price return data suffices; no new liquidity/cap source or future market-cap information required. Do not replace benchmark after seeing results. At dates with insufficient history, use exactly one documented common eligibility/warm-up rule; no backfill.

**Fixed random seeds** (pre-register on D1): `7, 11, 19, 23, 31, 43, 59, 71, 83, 97`. Rebalance/reselection events and universe eligibility must match A2/A3. Aggregate median, range and IQR across **10 random full OOS backtests**. Ten is a quick-sprint robustness comparison, **not** a precise estimate of a universal random-selection distribution.

### 2.3 Structural outcomes (all selection dates)

- **Coverage objective:** `sum_i min_{m in M}(1-rho[i,m])`; also mean nearest-representative correlation distance over all 30 equities. Lower is better under this exact objective. Full 30 trivially achieves zero and must **not** be called a fair K5 winner on this score.
- **Diversification:** pairwise intra-selected correlation (mean/median); effective number of positions `1/sum_i w_i^2` where valid; portfolio HHI `sum w_i^2`.
- **Stability:** selection overlap/Jaccard on adjacent 20-day reselections; number of stock changes per reselection.
- Optional *descriptive only*: covariance condition number (unstable to number of assets, use caution comparing K5 vs 30).

**Do not use future realized returns in the selection score**; draw original selection dates and eligible/correlation prefix from the baseline audit.

### 2.4 Portfolio outcomes

Same OOS dates and portfolio mechanics for all arms. Record:

`NAV, annualized return, annualized volatility, Sharpe, MDD, turnover/year, HHI, effective holdings, selection-switch count`.

For Random K5 show distribution summaries and where Proposed K5 falls; do **not** report best random seed only. Print comparative deltas (A3−A2, A3−Random median). Structural optimization of A3 implies an advantage in its **own objective** by definition — meaningful novelty is whether **portfolio results** or independent structural properties improve.

**D2–D3 acceptance:** A0/A2/A3 and all 10 A1 deterministic and auditable; same params and constraint family; clear results for K5-to-K5. If ML retraining is unexpectedly invoked, disable it for A rather than spending a day running redundant models.

## 3. D3–D4: Experiment B — Fair BL/MVO comparison and ML incremental value

### 3.1 Fix the exact same investable set and constraints

For every portfolio event use **Proposed K=5 + GOLD + VFF**, as selected by frozen A3 history. **Use the same 7-asset universe, data cutoff, rebalance schedule, position caps, group caps, VFF minimum, solver tolerance, weight cleanup, cash/turnover and risk-aversion conventions**.

Before running, export `docs/matched_constraints.md` with exact numeric values **read from frozen source/config**, not hand-invented. Confirm *feasible sets are identical*, though expected-return estimators can differ by hypothesis. If using any regime view, keep it **identical** in paired B1/B2 comparisons, or disable regime identically in both; never accidentally switch regime at the same time as ML.

### 3.2 Small optimization ladder

| ID | Model | Main comparison |
|---|---|---|
| **B0** | **MVO matched** on proposed 7, sample-mean expected return with frozen lookback | B0 vs B1 tests optimizer/prior trade-off |
| **B1** | **BL-no-ML**: same BL prior/rules, ML views removed; optional non-ML regime views held fixed if enabled for B2 | B1 vs B2 isolates ML-view incremental value |
| **B2** | **BL+ML**: matching prior/covariance/constraints plus frozen XGBoost views & confidence | Main ML test |
| **Reference only** | Legacy full-32 MVO and Hybrid / EW of frozen 12/10 | Descriptive; **NOT matched attribution** |

**Critical no-view rule:** the existing implementation contains **17** no-view situations that fall back to sample mean. When defining new B1, ensure no-ML case computes BL prior-only posterior if no non-ML views; do not rename this legacy fallback `BL-no-ML`. Preserve the legacy pipeline and write the ablation variant separately.

**Confounding guard:** B0 vs B1 can still differ in estimator/BL prior, which is the intended factor; solver/risk objectives and *feasible sets* must otherwise be the same. B1 vs B2 may differ **only** in ML views and parameters derived deterministically from those views. Same realized return path date and execution convention.

**What to reuse:** stored A3 selections, historical XGBoost forecasts/views from canonical baseline and BL inputs. If the new B2 on the identical 7 assets and baseline regime assumptions is equivalent to existing BL+ML, **verify numerical identity before reuse**; otherwise run one fresh B2, document the intentional difference. Do not rerun all ML models by default.

### 3.3 What to report

- Matched B0/B1/B2: IS and OOS `NAV, annual return, vol, Sharpe, MDD, turnover, HHI`, paired day-by-day returns and target weights.
- Primary effects: `B1−B0` and `B2−B1` for annual return, vol, Sharpe, MDD, turnover, HHI. Show both positive/negative.
- ML diagnostics already available: raw 324/635=51.02%, filtered views 175/347=50.43% in **04/10** report; **do not present those as updated 12/10 ML hit rates** unless recalculated from its corresponding prediction/realized-outcome files. ML prediction metrics are secondary to portfolio evidence.
- Legacy Hybrid can be compared as an end-to-end *descriptive* benchmark; do **not** attribute a Sharpe difference solely to hybridization given its different full-32 MVO branch.

**D3–D4 acceptance:** three matched variants and daily records reproduced with identical universe/constraints; at least two correctly interpreted increment comparisons; no mistaken no-view fallback.

## 4. D5: Lightweight confidence/regime probes — optional, never on critical path

Only if the current runner supports these by a simple switch and makes side effects explicit:

- **C1 Confidence:** same B2 forecast/views and risk rules; set confidence to a frozen fixed value vs current dynamic disagreement confidence. Fixed value chosen from existing IS/config definition; **never pick the best fixed confidence by OOS Sharpe**.
- **C2 Regime:** same B2 but toggle regime defensive view injection only, holding structural equity/VFF constraints fixed. If regime also changes other parameters, record the changed components and label as a **package effect**, not pure regime-view effect.
- **C3 Matched Hybrid (lowest priority):** combine matched B0 and B2 under same 7-asset universe and matched constraints, with frozen regime alpha. Run only if feasible by config and without introducing new optimizer implementation.

Maximum **two additional ablation comparisons** this sprint; if either requires substantive refactoring, **skip** and mark claims H4/H5 as provisional. Document `SKIPPED — TIME-BOXED / NO VALID SWITCH` rather than inventing a null result.

## 5. D5: Cost sensitivity and uncertainty — required, automated from saved outputs

### 5.1 Trading-cost sensitivity (do not confuse with executable fund modeling)

Use **0, 10, 25, 50 basis points per unit of one-way traded notional** as predeclared examples. For each rebalance, with pretrade-to-target weights:

\[
T_t = \tfrac12\sum_i|w_{i,t}^{target}-w_{i,t}^{pretrade}|,
\quad \text{tradedNotionalFraction}_t = \sum_i|\Delta w_i| = 2T_t.
\]

Under a per-side cost `c` of traded notional, an approximate NAV haircut is:

\[
NAV^{net}_{after\ trade} \approx NAV^{gross}_{before\ trade}\,[1-c\sum_i|\Delta w_i|].
\]

To avoid double-counting, **either** implement friction-aware holdings accounting consistently **or** transparently use an event-level multiplicative approximation on gross NAV and label it *approximate*, not an exact self-financing portfolio with costs. Exclude initial funding from annualized turnover as in the baseline, but explicitly state how initial transaction charges are handled in net NAV. Derive `cost_sensitivity.csv` with net NAV, net annual return, net Sharpe, net MDD by variant/cost and `break_even_cost` if obtainable without extra model fitting.

This **does not** validate actual fund dealing deadlines, gold SJC spread/slippage, transaction tax or price-vintage effects. Real-world costs can differ materially.

### 5.2 Paired block bootstrap (keep paired dates!)

- Resample **the joint daily return vector across compared strategies**, not each strategy independently. Use **moving block bootstrap** with **block length 10 trading sessions**, **1,000 replicates**, **fixed seed 20261014**, before viewing results. Alternative stable block bootstrap implementation acceptable only if documented in advance.
- For A compare Proposed K5 versus Simple K5, plus Proposed K5 vs the **median across the 10 prespecified Random K5 return streams** (describe that median construction explicitly as a descriptive aggregate).
- For B compare **B1 vs B0**, **B2 vs B1**. Recompute Sharpe/annual-return differences each replicate with same risk-free convention; use empirical percentile 95% CI. Also report raw effect sizes and drawdown differences descriptively (bootstrap MDD CI is sensitive to resampling method).
- An interval that includes zero indicates inadequate evidence of a decisive difference, **not** equivalence. These intervals are conditional on fixed market window/universe/data assumptions; they do not remove selection/post-hoc concerns.

If a median-random daily stream is considered not an investable strategy, treat it as an analytical benchmark, not trading P&L. Prioritize A3–A2 and B pair comparisons for inferential claims.

## 6. D6–D7: Validate, produce figures and issue an evidence-based verdict

### 6.1 No-leak / reproducibility assertions (mandatory)

- Selection inputs/data availabilities `<= cutoff` on each decision date, and correlation windows `<=t−1` where prescribed.
- 5-day ML label end strictly before decision; fit scaler on allowed fit rows only; no OOS training/tuning.
- Target weights formed after information; executed at next close; portfolio holds shares/units between rebalances; correct crossing IS→OOS without NAV reset in simulated holdings.
- `sum(w)=1`, `w>=0`, per-stock/group caps at trade date within frozen numerical tolerance; no post-cleanup cap breach.
- Same OOS dates for all matched comparisons; no look-ahead in Simple/Random selections; no accidental mixing of 04/10 and 12/10 baselines.
- Equal inputs/config/seeds must yield identical daily returns and weights to the prescribed tolerance. Independently recalculate one NAV path and at least one BL posterior/no-ML posterior case from logs.

Any substantial unexpected disagreement blocks release; record it, **never hide it to meet D7**.

### 6.2 Figures and tables (keep the package lean)

- **Table 1:** frozen sample and baseline (12/10), clear *legacy unmatched* labels.
- **Table 2:** K5 structural coverage, selection stability, diversification (A1 distribution).
- **Table 3:** matched asset-selection portfolio metrics (A0/A1/A2/A3).
- **Table 4:** matched optimizer ladder B0/B1/B2, with effect sizes.
- **Table 5:** cost sensitivity and paired-bootstrap CIs (can split in paper later).
- **Figure 1:** NAV + drawdown overlay for mandatory A/B matched arms (avoid clutter; separate panels per experiment).
- **Figure 2:** selection coverage/stability; optional confidence/regime one compact figure if actually run.

### 6.3 Final report template — `core_experiment_report.md`

```text
1. Scope, freeze reference and deviations
2. A: selection setup, structural results and portfolio results
3. B: matched-constraint definition and optimization ladder
4. Optional mechanisms actually executed (or explicitly skipped)
5. Costs, uncertainty and realistic interpretation
6. Results by H1–H6: supported / mixed / not supported / not tested
7. Baseline limits: static universe, assumed availability, price adjustment, GOLD/VFF trading
8. Paper-ready tables, figures, exact run IDs and hashes
9. Outstanding issues and recommendation
Final line: READY FOR PAPER REVISION or NOT READY FOR PAPER REVISION
```

**Release conditions:** A and B completed and verified; gross/core outcomes and zero-cost comparison reconciled; cost/bootstrap files present; timing, weights and returns internally consistent; unsupported claims not presented as proven; all runs attributable to frozen source/config. Weak/negative research effects do **not** block writing — they change what the paper may claim.

## 7. Workday checklist and time-control rules

| Day | Planned work | Required checkpoint |
|---|---|---|
| **D1** | Freeze baseline, verify 12/10 metrics; lock constraints, seeds and runner | Stable `experiment_plan.json`, baseline replay |
| **D2** | Run all A selections; structural metrics and check no-leak | `selection_structure.csv` + A selection histories |
| **D3** | Complete A portfolio runs; build B0/B1/B2 configs | `selection_portfolio_metrics.csv`; matched config |
| **D4** | Finish B comparisons, logs, effect sizes | `optimizer_ladder_metrics.csv` and daily returns |
| **D5** | Costs and bootstrap; if spare time 1–2 config-only probes | `cost_sensitivity.csv`, `uncertainty_intervals.csv` |
| **D6** | Independent consistency checks, plots, summary | Audit log + tables/figures |
| **D7** | Buffer for failed mandatory reruns; hand off report | Final archive + readiness line |

**Priority order if capacity tight:** (1) causal/metric correctness → (2) A and B → (3) cost and uncertainty → (4) optional confidence/regime → (5) extra pictures. Drop (4) first; never drop validity checks or hide missing mandatory work. If code or data unexpectedly prevent A/B, report the blocker, actual time spent and honest revised estimate; do not certify READY under pressure.

**Do not:** retune alpha/K/hyperparameters on OOS; search hundreds of baselines and showcase the winner; retrofit explanatory stories; expand geography; build a new crawler; refit the original July period; introduce another ML algorithm; call results “point-in-time verified,” “cost-free executable,” or “evidence that all modules work”.

**Suggested work communication:** Send supervisor a brief end-of-day update with `completed runs / failures / next checkpoint` and attach only the changed registry rows and summary tables, not every raw file.

## 8. Immediately after this sprint (parallel paper-writing track)

- Start revising title/abstract/contributions/method and notation on **D1**; update tables only when A/B pass.
- **D7–D12 target:** compile the existing manuscript + updated baseline + minimum extra experimental tables, discuss null results and limits, align Sharpe formula, view transformation (`tanh` vs manuscript Eq. 5), optimizer penalty and alpha interpretation.
- Treat data/publication timing, full PIT universe, real GOLD/VFF trading implementation as **limits/future work**, not completed checks. If the target journal requires stronger realism, decide on that after assessing this draft, not by silently extending the core experiment sprint.

---

**End-of-guide rule:** the goal is a defensible **paper revision backed by a small number of decisive experiments**, not an indefinitely expanding quantitative finance platform.
