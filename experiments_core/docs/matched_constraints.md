# Matched constraints

All A/B variants use the frozen optimize_weight_ranking function.

| Parameter | Value |
|---|---|
| risk_aversion | 1.5 fixed |
| max_weight | 0.50 all assets |
| min_defensive_weight | 0.15 nominal |
| max_nondefensive_exposure | 0.70 incl GOLD |
| defensive_assets | VFF only; effective floor 0.30 |
| weight_cleanup | 0.01; retain feasibility |
| constraint_tolerance | 1e-8 |
| covariance | 20 daily information returns, regularized eigenvalue floor 1e-8 |
| prior | delta=2.5, tau=0.05, equal-weight active universe |
| regime views/risk adjustment | OFF all A/B |
| B2 confidence | saved ML dynamic confidence incl volatility dampener |

Final target feasibility is checked; holdings may drift between trades. Baseline legacy is descriptive only.
