# project_0.md — Integrated Long-Only Portfolio Optimization: Focused Revision Project

**Version:** 2026-10-14 — **Re-scoped plan**  
**Status:** Trusted computational baseline established *under declared data-availability assumptions*; core evidence sprint **not yet run**.  
**Primary source documents:** original `project_0.md` and `guide_0.md`; *Báo cáo Step 1* dated 04/10 and updated 12/10/2026, especially section 13.  
**Next instruction:** new `guide_0.md` — **Step 1: Core Evidence Sprint (5–7 working days)**.

> **Research object:** long-only portfolio construction and economic performance, **NOT** stock-return prediction as a standalone goal.

## 1. Research goal and proposed contribution

Build and empirically evaluate an **integrated portfolio-construction architecture for the Vietnamese market**, using complementary established modules:

1. Correlation-structure-based **representative asset selection** to reduce redundancy and dimensionality.
2. **Black–Litterman (BL)** with equilibrium prior and uncertain views to stabilize allocation relative to direct sample-mean MVO.
3. **XGBoost-assisted views** as inputs to BL; not a standalone alpha/stock forecast contribution.
4. **Confidence-aware view weights** based on ensemble disagreement.
5. **Long-only risk limits** and defensive assets (GOLD/VFF).
6. **Regime-aware defense and BL/MVO Hybrid** for risk/upside trade-offs.

Potential contribution = **architecture + measured incremental value** of its indispensable layers under walk-forward evaluation. No claim of inventing a new BL theory, new ML model, causal market mechanism, guaranteed profit or cross-market generality.

### Main research question

> Does the proposed integrated, long-only portfolio-construction pipeline deliver useful risk-adjusted/downside performance on Vietnamese-market data; and which of its major layers measurably add value under **matched, causal, frozen** experiments?

### Hypotheses to test, not results to force

- **H1:** correlation-based representative K=5 is structurally/economically superior or competitive with simple/random K=5 and informative relative to Full 30.
- **H2:** under matched assets/constraints, BL allocation is more stable or risk-efficient than sample-return MVO.
- **H3:** adding XGBoost BL views improves the otherwise identical no-ML BL portfolio.
- **H4/H5:** confidence and regime/risk controls improve downside/risk-adjusted outcomes (optional mechanism tests in this sprint; claims must be proportionate to tests actually run).
- **H6:** full architecture maintains economically meaningful OOS performance, **subject to explicitly stated** transaction-cost, universe and price-availability limitations.

Negative, mixed and statistically inconclusive findings are acceptable scientific findings. Do not tune to make hypotheses pass.

## 2. Architecture, operating setup and boundaries

### 2.1 Existing system — preserve it

- Equity set: **static list of 30 stocks** (recorded as VN30 proxy, not point-in-time VN30 members), plus **GOLD** and **VFF**; reference VNINDEX calendar.
- Representative selection: `K=5`, minimize `sum_i min_{m in M}(1 − corr(i,m))` over all size-5 subsets; every **20 trading sessions**; historical correlation only. This is **correlation coverage / medoid-like selection**, not clustering/PAM.
- ML: XGBoost ensemble **5 members**; **5-trading-session** return target; retrain every **10 sessions**; ensemble disagreement determines view confidence.
- Allocation: BL posterior + constrained long-only optimization; separate MVO branch; regime-related defensive views; Hybrid with coefficients **alpha normal/stress/crisis = 0.6/0.3/0.1**; portfolio rebalance every **5 sessions**.
- Frequent parameters retained: covariance lookback **20 sessions**, `tau=0.05`, BL `delta=2.5`; other parameter, confidence, regime and position limits read **unchanged from frozen run configs** rather than reconstructed from this summary.
- **Important asymmetry:** EW/MVO currently operate on **32 assets**; BL usually on **Proposed K=5 + GOLD + VFF = 7 assets**; legacy Hybrid mixes the two. Therefore raw MVO-vs-BL/Hybrid comparisons are **not** clean causal attributions.

### 2.2 Frozen temporal/data contract (baseline 12/10)

- Active canonical run: `availability-observed-contract-20261012T233110`.
- Reported source location: `readiness_20261012/candidate_workspace/`; use actual preserved snapshot/config/hash in evidence bundle, **not** old July CSVs.
- Market matrix: **1,568 sessions × 32 assets**, from **14/01/2020 to 29/04/2026**.
- IS portfolio NAV: **18/02/2020–29/09/2023**, **906** daily returns after initialization.
- OOS NAV anchor **29/09/2023**, **641** returns **02/10/2023–29/04/2026**.
- Decision cutoff assumed **18:00 Vietnam time**. VFF observations become information-eligible **after at least five observed market sessions** or later provider record timestamp; GOLD close on D becomes eligible **D+1**. Decision-information inputs separate from portfolio valuation stream.
- New target weights after close(t), assumed execution at close(t+1); new holdings first earn `(t+1 → t+2)` return. Historical asset availability is **policy-declared, not verified from source-native publication timestamps**.
- Baseline results **gross of transaction costs**; historical 30-stock set static; provider adjusted-close may incorporate revisions not proven point-in-time; GOLD/VFF transaction execution/spreads not yet modeled.

## 3. Actual current project status (12/10 report)

### 3.1 Completed **and reported** under prior integrity Step 1

- Immutable legacy archive of **631 items**, with commit/hash/provenance.
- Historical retraining from source/data commit `71cc107`, no cache; weights/views/metrics matched recovered logs, though original environment and five separately fitted historical alpha cases are unavailable.
- Timing/leakage corrections: no same-period future return; 5-day target embargo; training-vs-validation label overlap corrected; scaler train-only; EMA/MACD inference consistent with training.
- Representative K=5 solutions and BL posterior audited; corrected holdings-based NAV, constraints and turnover.
- Data: VFF source identity improved; GOLD SJC HCMC sell-price secondary archive (GiaVang.tv, **2,343 calendar days 12/2019–04/2026**); KBS adjusted close normalized without second rounding; no double-add of dividends.
- Availability-policy lineage checked (**50,176 records**); according to report: **35/35** tests, **42/42** independent checks, **21/21** reproducibility checks; two new runs produced **13 byte-identical CSVs**.

**Evidence boundary:** these are findings **reported by the student**. The supplemental ZIPs/code, primary provider vintages and historical first-release timestamps have not been independently verified in this conversation. Historical-price accuracy, availability and fund tradeability are not certified.

### 3.2 Current **OOS gross** results to replace old manuscript numbers

| Strategy | NAV | Annual return | Annual volatility | Sharpe | MDD | Annual turnover |
|---|---:|---:|---:|---:|---:|---:|
| Equal Weight | 1.7278 | 23.98% | 18.37% | 0.946 | −17.08% | 0.628 |
| MVO (legacy full 32) | 3.3904 | 61.61% | 33.08% | 1.441 | −30.18% | 23.363 |
| BL+ML (legacy proposed K=5) | 1.8136 | 26.37% | 13.33% | 1.385 | −9.51% | 8.200 |
| Hybrid (legacy) | 2.7044 | 47.86% | 21.38% | 1.665 | −16.13% | 16.613 |

**Current IS context:** BL+ML Sharpe **0.617** vs EW **0.651**; MVO **1.146**, Hybrid **1.241**. Mixed IS/OOS evidence must be described transparently.

**Empirical interpretation, not component proof:** BL+ML has lower volatility/drawdown than MVO in unmatched setups but **lower Sharpe (1.385 vs 1.441)**; Hybrid has highest Sharpe among these four, with material turnover and meaningful drawdown. Baseline is before costs. Comparison to manuscript historical BL path shows OOS daily-return correlation **0.642** over a common period: results are sensitive to the revised data/protocol.

### 3.3 Outstanding limitations (do not claim they were solved)

1. **Data availability is an assumption**, not a certified vintage archive (VFF and GOLD first publication not reconstructed).
2. Adjusted-close factors / corporate-action ledger / total-return identity not proven; historical revision vintage unspecified.
3. Static 30-stock set creates potential **survivorship bias**; full point-in-time constituent rebuilding is not part of this sprint.
4. Fund/gold tradability, VFF subscription/redemption deadlines, spread/slippage and real trade execution are not simulated; cost sensitivity is a simplified stress test, not a fully executable fund model.
5. Provenance of certain original parameter decisions predating OOS remains unknown; do not retrospectively invent IS-tuning evidence.
6. The original paper's equations, Sharpe convention, view transformation and labels need alignment with corrected code (previous audit identified discrepancies).
7. Component attribution currently missing: selected K=5 vs alternatives; MVO vs BL under matched constraints; ML incremental value; confidence/regime incremental value.

## 4. New reduced experimental program — **5–7 working days total**

**Principle:** no new architecture, no novel ML or parameter search, no additional countries, no complete raw-data rebuild. Freeze the **12/10** baseline and run only the experiments necessary to support the journal revision.

### NEW STEP 1 — Core Evidence Sprint (mandatory; 5–7 working days)

**Experiment A — Representative selection:** Full 30, Random K=5 (**10 precommitted seeds**), Simple K=5 (**20-day lowest trailing volatility** using information through t−1), Proposed correlation-cover K=5. One common **BL-prior/no-ML** optimizer and matched risk rules, no ML/regime/hybrid, identical return/calendar/data cutoff, no cost at baseline. Score structural representation and portfolio metrics. K=5-to-K=5 is the clean comparison; Full 30 is a universe-size context baseline.

**Experiment B — Fair optimizer ladder:** Fix *Proposed K=5 + GOLD + VFF* and identical constraints, rebalance dates and risk setup. Run **matched MVO**, **BL no ML**, **BL+ML**. Only the ML-view set should differ in noML vs BL+ML; existing regime views (if present) must be handled **identically in both**. Do not mislabel the legacy no-view **sample-mean fallback** as BL prior. Keep existing Hybrid/full-MVO results descriptive; a matched-universe hybrid may be added only if already config-supported.

**Lightweight corroboration, time-boxed:**
- Fixed vs dynamic confidence and/or regime defense on/off **only if configurable without substantial coding**; else explicitly leave claims tentative.
- Trading-cost scenarios **0, 10, 25, 50 bps** computed from saved trades/weights and an explicit per-side convention; net metrics.
- **Paired block bootstrap** of OOS return differences (pre-fixed block size, seeds, replicates); CIs for effect sizes. Descriptive evidence rather than automatic significance claims.
- No full rebuild of point-in-time universe, publication vintages or fund subscription microstructure this sprint; include limitations and optional already-available snapshot check.

**Non-negotiable controls:** same frozen inputs, historical-only features at decision cutoff, execution causality, parameter freeze, no OOS model/alpha/K tuning, consistent comparisons and constraint audits, deterministic seeds. If experiments are negative, report that result rather than expanding scope.

**Workday schedule:** D1 freeze/config checks; D2–D3 A; D3–D4 B; D5 costs/bootstrap/quick toggles; D6–D7 (if needed) verification/tables/handoff. Detailed commands, outputs and acceptance gates: `guide_0.md` new.

### NEW STEP 2 — Paper revision track (parallel, draft D7–D12)

- Rewrite **Abstract, Introduction, contributions** around integrated portfolio construction.
- Correct data/clock, pricing policy, equity universe, BL model, formulas, Sharpe calculation, benchmark specifications.
- Methods: causal walk-forward and separate **existing descriptive benchmarks** from **matched ablations**.
- Results: updated 12/10 baseline + A/B outcomes + available confidence/regime + costs/bootstrap, clearly marked.
- Discussion: evidence that supports or contradicts H1–H6, risk/upside trade-off, limitations, no universal/executable claims.
- Finish figures, reproducibility appendix, risk-of-bias statement and submission formatting. Writing starts D1, **not** a separate 10-step research cycle.

### Deferred / explicitly *not required* for the 5–7-day experiment scope

- Full historical point-in-time VN30 reconstruction, corporate-action vintage archive, verified VFF/GOLD publication timestamp archive.
- Execution-level GOLD/VFF microstructure/slippage/fund dealing calendar; cross-market extension.
- Multi-model ML competition, tuning new XGBoost/confidence rules, optimizing K or alpha on OOS.
- Large regime grid, full standalone ML-prediction paper, repeated exploration until significance is found.

These are **limitations and possible follow-up research**, not items silently certified as complete. If a journal demands them, scope must be revisited openly.

## 5. End-of-sprint deliverables and scientific decision gate

Required outputs:

- Frozen provenance: `run_config.json`, input/source hashes, seed/env manifest, baseline replay log.
- `selection_structure.csv`, `selection_portfolio_metrics.csv`, `selection_history_comparison.csv`.
- `optimizer_ladder_metrics.csv`, `ablation_daily_returns.csv`, `ablation_weights.csv`.
- `cost_sensitivity.csv`, `uncertainty_intervals.csv` and figures (NAV, drawdown, selection coverage, mechanism effects as tested).
- `core_experiment_report.md`: setup, fairness, results and effect sizes, rejected/unsupported claims, known limitations, paper-ready tables.
- `experiment_registry.csv` and `deviations.md`: every executed run and departure from prespecified plan.

**Ready for writing/submission polishing** when mandatory A and B run reproducibly, constraint/temporal gates pass, effects are honestly reported (even if negative), cost/uncertainty diagnostics are produced, and the manuscript can distinguish supported statements from mere hypotheses. `READY FOR PAPER REVISION` is **not** equivalent to “validated executable trading strategy”.

**Risk/time contract:** D1–D7 covers the **incremental experiment scope**, *not guaranteed wall-clock completion regardless of bugs/data*. Remove optional mechanism probes first if time constrained. Never suppress a genuine integrity blocker to satisfy the deadline.

## 6. Source-to-status reconciliation

- **Original `project_0.md`:** retains the core thesis and hypotheses, but the previous 11 sequential steps are replaced here with the focused A/B experiments and parallel writing.
- **Original `guide_0.md`:** its old Step 1 integrity tasks are **already addressed at reported/conditional level** by the 12/10 report. The new `guide_0.md` starts the next work package and does not instruct the student to redo the audit.
- **12/10 report, §13:** provides the active availability contract, readiness conclusion, run identity and current results. §§2–11 describe inherited 04/10 audit; §12 describes **old 04/10 metrics** and should not be copied into the new paper as active baseline.
