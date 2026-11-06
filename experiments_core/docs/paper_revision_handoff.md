# Paper revision handoff

## Proposed title

Integrated Long Only Portfolio Construction for the Vietnamese Market with Correlation Coverage Selection and Black Litterman Views

## Proposed abstract

We evaluate an integrated long-only portfolio construction pipeline on a fixed 30-stock Vietnamese equity proxy with gold and a bond-fund NAV proxy. The walk-forward protocol separates decision information from portfolio valuation, uses next-close execution, and preserves holdings between rebalances. Matched experiments compare representative selection against simple and random K=5 alternatives, and sample-mean allocation against a Black–Litterman equilibrium prior with and without saved causal XGBoost views. Over 641 out-of-sample returns, correlation-coverage selection improves its structural coverage and selection stability, while economic performance is mixed. The prior-only allocation has lower volatility, concentration and turnover than matched sample-mean allocation. ML views improve gross Sharpe from 1.175 to 1.367 but increase turnover; the prior-only allocation has higher net Sharpe at 25–50 bps per side. All paired moving-block-bootstrap intervals for annual-return and Sharpe differences include zero. Findings support cautious architectural and risk-allocation claims under declared availability assumptions, rather than statistical superiority or executable trading profitability.

## Contributions supported at current scope

- A reproducible integrated construction architecture and explicit information/execution contract.
- Matched structural and portfolio comparisons for selection, with all ten random seeds reported.
- Estimator/prior and ML-view incremental effects under identical constraints, including costs and uncertainty.

## Method notation to align

Daily mu/Q and daily-return covariance; pi = delta Sigma w_eq; no-view posterior = pi. Sharpe uses mean daily excess return divided by sample daily volatility and multiplied by sqrt(252), with compounded rf=6% annual. The frozen objective is muᵀw minus gamma wᵀSigma w (gamma 1.5 in the controlled ladder). Describe tanh-scaled ML views, confidence/Omega convention, equal-weight prior proxy, effective VFF floor 30%, and conditional legacy Hybrid alpha semantics explicitly.

## Results and limitations to preserve

Use Table 1 legacy as descriptive, Tables 2–4 matched for attribution, and cost/bootstrap tables for limits. Do not say ML/BL/proposed selection is universally superior. Distinguish the 2026-10-12 baseline from the 2026-10-04 audit and old manuscript values. Static constituents, publication timing assumptions, revised adjusted-close vintages, gold/fund execution and pre-OOS parameter-choice provenance remain limitations. The source manuscript is not silently rewritten by this handoff.
