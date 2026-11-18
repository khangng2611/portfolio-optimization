# Verification results

PASS, 2026-11-04. 4897 independent assertions; 18 unittest cases passed (12 C + 6 inherited accounting/research tests). Exact command: venv/bin/python -B -m extensions_C_v1.verify_evidence. Full test output: qa/tests.log, included in evidence archive.

- Both recorded C1 runs succeeded; 12 numerical CSV files are byte-identical.
- Saved pre-result source snapshots/protocol hashes and every recorded run-artifact hash remain intact. Original inputs and private C snapshots match all baseline hashes after execution.
- All 310 C1 targets have exactly seven positive holdings, VFF .30, others .70/6; full investment, long-only, .50 cap and minimum target HHI checked.
- All 930 strategy-event groups retain 32 assets, including exits/entries, and sum(abs(traded weights)) = traded notional = 2 × turnover. Event totals repeat across asset rows; deduplicate before summing.
- Independent post-close unit × price + cash reconstruction matches C1 NAV within 1.1e-13; runner's separate unit engine error was 8.66e-14.
- All 48 strategy/phase/cost rows independently recomputed for N, NAV, CAGR, volatility, Sharpe and drawdown within 1e-10. Frozen B1/B2 grids also reconcile against accepted Step2 controls inside each run.
- Toy tests cover prior-only membership, next-close new-position timing, full entry/exit union, initial and terminal cost, hand-calculated metrics, paired bootstrap, price-index/missing-rights rejection and C2 shorter common-sample recomputation without gap bridging.
- C2 status/nulls/header-only daily output and all 641 not-evaluable dates verified. No empirical C2 index performance computed.

Independent read-only review found no critical/important defect. It confirmed C1 weights, menu identity, units, repeated CSVs and interpretation limits. Metadata completeness checks cannot verify the truth of a claimed license or vintage; source evidence must be reviewed before future C2 admission.

Report visual QA: six DOCX-rendered pages inspected; no clipping, split rows or missing Vietnamese glyphs. Source and rights limitations are disclosed, not resolved by a software PASS.
