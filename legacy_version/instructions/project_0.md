# project_0.md

# Project: Integrated Long-Only Portfolio Optimization for the Vietnamese Market

## 1. Core idea

This project is **a portfolio-construction study, not a stock-return-prediction study**.

The central idea is to build and empirically validate an **integrated long-only portfolio optimization framework** in which several established quantitative techniques are combined because each addresses a different practical weakness of portfolio construction:

1. **Representative asset selection using correlation structure**
   - reduce redundancy in the investable equity universe;
   - reduce dimensionality and estimation noise;
   - retain stocks that collectively represent the correlation structure of the broader VN30 universe.

2. **Black–Litterman portfolio optimization**
   - avoid relying directly on unstable sample expected returns;
   - combine an equilibrium prior with uncertain views;
   - obtain more stable expected-return estimates for portfolio construction.

3. **XGBoost-assisted Black–Litterman views**
   - use machine learning as a systematic **view generator**, not as a standalone trading system;
   - convert noisy short-horizon forecasts into BL views rather than feeding them directly into an unconstrained optimizer.

4. **Confidence-aware view integration**
   - use ensemble disagreement to modulate how strongly each ML-generated view influences the BL posterior.

5. **Practical long-only risk constraints and defensive assets**
   - produce implementable allocations;
   - control concentration and equity exposure;
   - provide downside protection.

6. **Regime-aware defensive allocation / hybridization**
   - adapt the portfolio when volatility and drawdown indicate stress;
   - balance upside capture and downside protection.

The scientific contribution is therefore the **architecture and empirical validation of the full portfolio-construction pipeline**, not the invention of any single component.

---

# 2. Main research statement

A suitable central statement for the paper is:

> **This work investigates whether an integrated portfolio-construction framework combining correlation-structure-based representative asset selection, Black–Litterman allocation, machine-learning-assisted views, and practical risk controls can produce robust long-only portfolios under a strict walk-forward setting in an emerging market.**

The paper should not be framed as:

> “Can XGBoost accurately predict stock returns?”

Instead:

> **Can multiple complementary portfolio-optimization techniques be integrated into a coherent decision pipeline that produces economically meaningful, risk-controlled long-only portfolio performance?**

---

# 3. Research hypotheses

## H1 — Representative asset selection improves portfolio construction

> A correlation-structure-based representative asset set can preserve useful diversification information while reducing dimensionality and estimation noise relative to operating directly on the complete equity universe.

This hypothesis should be tested at both:
- **structure level**: representation / correlation coverage;
- **portfolio level**: risk-adjusted performance, weight stability, turnover.

---

## H2 — Black–Litterman provides a more robust allocation layer than direct mean–variance optimization

> Using an equilibrium prior and uncertain views should produce more stable long-only allocations than relying primarily on short-window sample expected returns.

The key comparison is not raw return alone.

Relevant outcomes include:
- volatility;
- drawdown;
- Sharpe / Sortino;
- concentration;
- turnover;
- weight stability.

---

## H3 — XGBoost adds value as a BL view generator

> Even when standalone ML forecasts are noisy, they may provide useful directional / relative information when incorporated as uncertain Black–Litterman views.

The ML component should therefore be evaluated by its **incremental portfolio value**, not only by prediction accuracy.

The current directional hit rate of approximately 51.9% should be reported transparently.

The important question is:

> Does adding ML-generated views improve the portfolio relative to an otherwise identical no-ML BL system?

---

## H4 — Confidence-aware views improve the use of noisy forecasts

> Ensemble disagreement may provide information about forecast reliability, allowing BL to place less weight on uncertain views and more weight on relatively reliable ones.

This is an important supporting mechanism, but not the sole story of the paper.

---

## H5 — Practical risk controls improve downside robustness

> Long-only constraints, defensive assets, regime-aware views and hybrid allocation can reduce drawdown and volatility while preserving economically meaningful upside participation.

This should be treated as the **risk-management layer** of the architecture.

---

## H6 — The integrated system produces robust out-of-sample long-only portfolio performance

> The complete framework should demonstrate economically meaningful performance under a strict walk-forward protocol after accounting for data timing, survivorship bias, portfolio turnover and transaction costs.

Use language such as:
- “out-of-sample economic performance”;
- “walk-forward portfolio performance”;
- “empirically validated long-only portfolio construction”.

Avoid:
- “proven profitable”;
- “guaranteed P&L”;
- claims of universal market superiority.

---

# 4. Conceptual architecture

The paper should explicitly connect each problem to the technique intended to address it.

| Portfolio problem | Technique |
|---|---|
| Large / redundant equity universe | Correlation-structure-based representative asset selection |
| Covariance / mean estimation instability | Dimensionality reduction + Black–Litterman |
| Need for systematic forward-looking views | XGBoost-generated return views |
| Noisy ML forecasts | Confidence-weighted BL uncertainty |
| Concentration / impractical allocations | Long-only constraints and position limits |
| Market stress / non-stationarity | Defensive assets and regime-aware views |
| Trade-off between upside and robustness | BL/MVO hybrid allocation |
| Real investment objective | Walk-forward portfolio P&L and risk-adjusted performance |

The **hero of the paper is the architecture**, not a single algorithm.

---

# 5. Current status

## 5.1 Existing dataset and evaluation design

Current draft uses approximately:

- Vietnamese equity market;
- VN30 equity universe;
- additional assets:
  - GOLD;
  - VFF bond fund;
- daily OHLCV data;
- sample from approximately January 2020 to April 2026;
- in-sample period: January 2020 – October 2023;
- out-of-sample period: October 2023 – April 2026;
- expanding-window walk-forward ML training;
- 5-day forward-return prediction horizon.

---

## 5.2 Existing portfolio architecture

The current implementation already contains:

1. correlation-distance-based representative asset selection;
2. exhaustive selection of `K = 5` representative stocks;
3. periodic stock reselection;
4. technical feature engineering;
5. XGBoost ensemble forecasting;
6. ensemble-disagreement confidence;
7. conversion of forecasts into BL views;
8. Black–Litterman posterior;
9. constrained long-only optimization;
10. GOLD / VFF diversification;
11. regime detection;
12. defensive BL view injection;
13. standard MVO branch;
14. regime-dependent BL–MVO hybrid allocation.

Current operating frequencies:

- portfolio rebalance every 5 trading days;
- ML retrain every 10 trading days;
- representative-stock reselection every 20 trading days.

---

## 5.3 Current reported OOS performance

The current manuscript reports approximately:

| Strategy | NAV | Ann. Return | Ann. Volatility | Sharpe | MDD |
|---|---:|---:|---:|---:|---:|
| Equal Weight | 1.82 | 27.2% | 17.1% | 1.15 | -17.3% |
| MVO | 3.73 | 69.4% | 31.8% | 1.64 | -15.0% |
| BL+ML | 1.90 | 29.3% | 12.0% | 1.71 | -7.1% |
| Hybrid | 2.86 | 52.3% | 21.0% | 1.83 | -11.4% |

The current result pattern is therefore not mainly:

> “ML predicts returns accurately.”

It is closer to:

> **The integrated BL-based construction substantially reduces portfolio risk and drawdown, while the hybrid architecture recovers more upside and maintains strong risk-adjusted performance.**

This should become the empirical story.

---

# 6. Current weaknesses to solve before journal submission

## 6.1 The manuscript currently over-emphasizes stock prediction

The current writing makes XGBoost appear to be the main contribution.

This is misaligned with the actual project design.

Revision needed:
- move portfolio construction to the center of Introduction, title, abstract and contribution statement;
- present ML as a view-generation module.

---

## 6.2 Component attribution is currently insufficient

The current system combines many techniques simultaneously.

The paper does not yet establish how much value comes from:

- representative asset selection;
- BL itself;
- ML-generated views;
- confidence weighting;
- defensive constraints;
- regime views;
- hybrid blending.

A journal version needs controlled ablations.

---

## 6.3 Asset-selection contribution is under-tested

The current method uses a correlation-based coverage objective to select `K=5` representative stocks.

This is an important component of the intended research story, but the current manuscript does not adequately test whether it improves:

- representation of the VN30 correlation structure;
- covariance estimation;
- portfolio stability;
- risk-adjusted performance;
- turnover;
- diversification.

This becomes a major experiment in the revised paper.

---

## 6.4 Terminology must be precise

The existing method is best described as:

> **correlation-structure-based representative asset selection**

or:

> **correlation-based medoid-like coverage selection**

Do not call it “correlation clustering” unless a clustering algorithm is actually introduced and tested.

---

## 6.5 Missing no-ML BL benchmark

A BL system with the same universe and same constraints but **without ML views** is required.

Otherwise the paper cannot show whether XGBoost adds incremental portfolio value.

---

## 6.6 Missing matched-constraint baselines

Comparisons must separate:
- optimization method;
- asset universe;
- structural constraints;
- defensive allocations.

A standard MVO with different constraints is not enough.

---

## 6.7 Confidence mechanism needs direct validation

The existing ensemble-disagreement confidence should be tested to determine whether confidence is actually related to:
- forecast error;
- hit rate;
- economic usefulness.

---

## 6.8 Backtest integrity needs audit

The manuscript's pseudocode creates possible ambiguity regarding whether weights determined using data at `t` are applied to returns already realized at `t`.

The implementation must guarantee:

> information through `t` → decision after `t` → execution from `t+1` → first earned return after execution.

---

## 6.9 Survivorship bias

The VN30 universe must be checked for point-in-time constituent membership.

Using final/current constituents historically could bias results.

---

## 6.10 Transaction costs

A 5-day rebalance schedule requires:
- turnover measurement;
- transaction-cost sensitivity;
- net portfolio results.

---

## 6.11 Statistical uncertainty

Current tables report point estimates only.

A journal version should include dependence-aware uncertainty / bootstrap analysis.

---

## 6.12 Numerical inconsistency

The current manuscript contains an MVO NAV inconsistency:

- main OOS table: approximately `3.73`;
- hybrid sensitivity at pure-MVO setting: approximately `3.57`.

This must be traced to the implementation and resolved.

---

# 7. Revised experimental plan

## STEP 1 — Backtest integrity and trusted baseline reconstruction

Purpose:

> Establish a causally correct, internally consistent and reproducible portfolio backtest before running any new experiment.

Tasks:
- freeze legacy code and outputs;
- verify feature timing;
- verify training-label embargo;
- verify execution timing;
- verify portfolio return calculation;
- reconcile MVO inconsistency;
- record universe construction;
- record parameter provenance;
- generate trusted baseline returns, weights, turnover and metrics.

Output:
- `step1_report.md`;
- trusted baseline datasets;
- integrity audit tables.

Detailed instructions: `guide_0.md`.

---

## STEP 2 — Validate representative asset selection

This step becomes central under the revised research story.

### 2.1 Compare selection approaches

At minimum compare:

1. **Full VN30**
2. **Random K=5**
3. **Simple benchmark selection**
   - e.g. largest-cap / highest-liquidity K where data permits
4. **Proposed correlation-structure representative K=5**

Optional:
5. K-medoids / hierarchical-clustering representative selection.

### 2.2 Structural evaluation

Measure:

- correlation-coverage objective;
- average distance from each VN30 asset to nearest representative;
- stability of selected assets through time;
- pairwise correlation among selected assets;
- covariance condition number;
- effective diversification / concentration metrics.

### 2.3 Portfolio evaluation

Run the **same downstream optimizer** for all selection methods.

Compare:
- return;
- volatility;
- Sharpe;
- MDD;
- turnover;
- concentration;
- weight stability.

Key principle:

> Only the asset-selection method should change.

---

## STEP 3 — Establish a fair portfolio-optimization ladder

Construct controlled models.

### A. Equal Weight
Reference benchmark.

### B. Standard MVO
Classical sample-based optimizer.

### C. Matched-constraint MVO
Same investable universe and practical constraints as the BL systems.

### D. BL Base / No ML
Equilibrium BL prior with identical universe and constraints; no ML views.

### E. BL + ML
Add XGBoost-generated views.

### F. BL + ML + dynamic confidence
Add disagreement-based uncertainty weighting.

### G. BL + ML + confidence + regime defense
Add regime-aware defensive views.

### H. Full hybrid system
Add regime-dependent BL/MVO blending.

Between adjacent models, change one conceptual layer where possible.

---

## STEP 4 — Evaluate the incremental role of XGBoost

The goal is not to prove high standalone prediction accuracy.

Evaluate:

### Prediction level
- MAE;
- RMSE;
- directional hit rate;
- sign / magnitude distribution;
- prediction stability.

### Portfolio level
Compare:

`BL Base` vs `BL + ML`

with everything else fixed.

Measure:
- Δ annual return;
- Δ volatility;
- Δ Sharpe;
- Δ MDD;
- Δ turnover;
- Δ concentration.

This is the primary evidence for the claim:

> XGBoost is useful as a BL view generator.

---

## STEP 5 — Validate confidence-aware view weighting

For every OOS forecast store:

- date;
- asset;
- prediction;
- realized forward return;
- ensemble disagreement;
- mapped confidence;
- forecast error;
- directional correctness.

Analyze confidence quantiles.

Report:
- hit rate by confidence quantile;
- MAE / RMSE by confidence quantile;
- correlation between confidence and forecast reliability.

Then compare:

- BL+ML with fixed confidence;
- BL+ML with disagreement-based confidence.

If the current confidence transformation does not show meaningful calibration, redesign it using IS/validation data only and freeze it before OOS testing.

---

## STEP 6 — Evaluate risk-management layers

Separate the contribution of:

1. structural long-only constraints;
2. defensive VFF allocation;
3. regime detection;
4. defensive BL views;
5. BL/MVO hybridization.

Measure:

- MDD;
- downside deviation;
- Sortino ratio;
- recovery time;
- volatility;
- equity exposure through time;
- return sacrificed for risk reduction.

The key result should explain the current pattern:

> BL-based construction provides downside robustness; hybridization trades some of that protection for greater upside participation.

---

## STEP 7 — Remove survivorship bias

Preferred:
- reconstruct point-in-time VN30 membership.

For each date:
- define eligible stocks using information available then;
- run representative selection only on eligible stocks.

Fallback robustness:
- freeze constituents using only information known at the beginning of the OOS period.

Report both if possible.

---

## STEP 8 — Transaction-cost and implementability analysis

Compute turnover at every rebalance.

Test multiple trading-cost assumptions.

Suggested sensitivity:
- 0 bps;
- 10 bps;
- 25 bps;
- 50 bps;

plus a Vietnam-specific scenario if an appropriately sourced cost model is available.

Report:
- net return;
- net Sharpe;
- net MDD;
- annualized turnover;
- break-even trading cost.

This is necessary before describing the system as practically implementable.

---

## STEP 9 — Statistical robustness

Because financial returns and 5-day decisions are dependent over time, use a dependence-aware method such as:

- moving block bootstrap;
- stationary bootstrap.

Estimate confidence intervals for:
- annualized return;
- volatility;
- Sharpe;
- differences between strategies;
- relevant downside metrics where feasible.

Also assess whether:
- ML views add statistically meaningful incremental value;
- proposed asset selection improves stability / performance;
- dynamic confidence improves on fixed confidence.

---

## STEP 10 — Temporal robustness inside Vietnam

Before adding another country, test whether results persist across different Vietnamese market conditions.

Possible analyses:
- rolling OOS windows;
- bull periods;
- corrections;
- volatility regimes;
- stress / crisis periods.

Question:

> Is the architecture useful across market regimes, or only during one favorable period?

---

## STEP 11 — Rewrite the journal paper

### Recommended narrative

1. Portfolio optimization is difficult because asset universes are redundant, expected returns are unstable and market regimes change.
2. Different quantitative techniques address different parts of this problem.
3. The paper integrates these techniques into one walk-forward long-only construction pipeline.
4. Correlation-based representative selection reduces dimensionality and redundancy.
5. BL provides a robust allocation layer.
6. XGBoost provides systematic but explicitly uncertain views.
7. Confidence and defensive mechanisms control how aggressively the system acts on those views.
8. Controlled ablations show the incremental role of each layer.
9. Portfolio-level P&L, downside risk and robustness — not standalone prediction accuracy — determine success.

---

# 8. Recommended research questions for the final manuscript

### RQ1
Can correlation-structure-based representative asset selection preserve diversification information while improving the stability and efficiency of long-only portfolio construction?

### RQ2
Does Black–Litterman allocation improve portfolio robustness relative to conventional mean–variance optimization under matched investment constraints?

### RQ3
Do XGBoost-generated views provide incremental economic value when incorporated into Black–Litterman rather than used as standalone return forecasts?

### RQ4
Do confidence weighting and regime-aware defensive mechanisms further improve downside robustness and risk-adjusted performance?

### RQ5
Does the complete integrated framework remain economically meaningful after controlling for transaction costs, historical index membership and sampling uncertainty?

---

# 9. Expected final evidence package

## Core tables

1. Data and point-in-time universe specification.
2. Parameter provenance.
3. Asset-selection structural comparison.
4. Asset-selection portfolio comparison.
5. Controlled optimization ablation ladder.
6. ML forecast diagnostics.
7. Fixed vs dynamic confidence.
8. Risk-management ablation.
9. Transaction-cost sensitivity.
10. Statistical confidence intervals.
11. Temporal-regime robustness.

## Core figures

1. Architecture: portfolio problem → technique → allocation.
2. Walk-forward timing diagram.
3. Representative-asset coverage / selection history.
4. NAV comparison.
5. Drawdown comparison.
6. Portfolio exposure through time.
7. Confidence vs forecast reliability.
8. Net performance vs transaction cost.
9. Optional rolling Sharpe / MDD by regime.

---

# 10. Publication positioning

The strongest journal positioning is:

> **Applied / computational portfolio construction with rigorous empirical validation in an emerging market.**

The paper should not claim:
- a new theory of Black–Litterman;
- a fundamentally new ML algorithm;
- universal market generalization.

It should claim, if supported by the completed experiments:

> **A carefully designed integration of representative asset selection, robust BL allocation, ML-assisted views and practical risk controls can produce stable, economically meaningful long-only portfolios under strict walk-forward evaluation.**

This framing is particularly suitable for journals that value:
- technically sound empirical research;
- computational finance;
- portfolio optimization;
- market-specific evidence;
- reproducibility and practical validation.
