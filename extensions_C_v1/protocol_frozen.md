# Frozen protocol for additional experiments C

Version C-v1, frozen 2026-11-04 Asia/Ho_Chi_Minh before computing C performance. User request in this chat authorizes implementing the attached experiment_1.md. This record is a post-design extension on an already examined holdout, not prospective preregistration or supervisor acceptance of results.

## Scope and source

C1 and C2 only. C3–C6 receive feasibility/design proposals and are not run. Existing Step 1/Step 2 evidence stays read-only. The exact assignment is copied to inputs/experiment_1.md and hashed in baseline_manifest.json. New namespace: extensions_C_v1. Local input snapshots are private research copies; source ownership, source restrictions and unverified original publication vintages remain documented limitations. No vendor raw data will be uploaded merely because it is publicly viewable.

Accepted baseline: availability-observed-contract-20261012T233110. Accepted B run: core-evidence-20261023T211011. Use its aligned valuation prices, eligibility policy/ledger, A3 dated memberships, B1/B2 decision/fill/target/trade/daily records, and configuration. Verify every resolved input against the original run hashes before simulation, with no fallback to current root datasets. No fresh ML fit or change to B1/B2.

## C1 fixed rule and clock

Label C1-FixedRule-K5-7. On every original five-session decision date, use the most recent A3 selection whose recorded selection_date is no later than that decision and whose history_end is strictly earlier. Original selection dates, original selection row identity, decision index and first effective fill are preserved in input snapshots. Target VFF=0.30; each of the five selected equities and GOLD=0.70/6; all others zero. This is a conditional weighting benchmark with active dated selection, not unconditional buy-and-hold and not equal 1/7.

Cash initially 1. At close t+1 old units earn the t→t+1 return before the new target executes; new units first earn t+1→t+2. Use the complete 32-ticker union so exits and entries are never omitted. Preserve one continuous IS/OOS holdings path. Target feasibility tolerance 1e-8, maximum position 0.50, non-VFF cap 0.70; drifting weights need not satisfy trade-time bounds between trades.

Annualization 252; sample standard deviation ddof=1; rf_daily=1.06^(1/252)-1. IS anchor 2020-02-18, 906 returns to 2023-09-29. OOS anchor 2023-09-29, 641 returns 2023-10-02 through 2026-04-29. One-way turnover is half the sum of absolute pretrade-to-target changes, annualized by 252/N. Initial funding excluded from turnover and charged once for costs in IS; no second OOS funding. Terminal close trades remain charged without inventing later returns.

Cost grid per side: 0,10,25,50 bps. Net return at execution date is (1+gross_return)*(1-c*sum_abs_trades)-1, using the frozen approximate gross-target event accounting, not a new self-financing execution-cost engine. All IS/OOS metrics, target and daily HHI, mean reciprocal positive HHI, actual units and cash, full trades and class exposures are saved. Report C1 minus B1/B2 effect sizes; CAGR differences in percentage points. Optional paired bootstrap is included: non-circular moving blocks 10, 1000 draws, one fixed seed 20261104, joint sampled indices within every pair. No rule/cadence changes after inspecting differences.

## C2 source selection and acceptance

Search first for official HOSE VN30TRI daily total-return history in VND with documented dividend treatment. Second eligible family is an official VN-Index total-return variant if verifiable. Select based on canonical definition, coverage and lawful research access, never observed performance. Sources with only charts, monthly points, missing dividend methodology, unknown vintage/record dates, inaccessible licensed history or unconfirmed rights fail the gate. Do not buy access, bypass authentication, infer vendor timestamps, backfill prices, reconstruct total return from the static stock universe, or relabel VNINDEX/VN30 price return.

A permitted input must supply index_date, index_level, vendor_record_date (or explicit missing-field issue), identifier, currency, total-return/dividend method, historical methodology/vintage and research-use permission. Public metadata alone is not a right to redistribute a full vendor series. Missing required metadata stops C2 calculation and produces C2_source_feasibility.md, C2_source_and_alignment.md and a source-status table with null metrics and reasons, not zero-return fabricated data.

If a valid series is available, reindex levels on the frozen valuation calendar and calculate one-session returns only when both adjacent levels exist. Preferred OOS has all 641 returns. If incomplete, select the longest contiguous eligible common-return interval (earliest tie), re-anchor all three paths at the preceding common session and recompute B1/B2 on that interval. Never fill missing returns with zero or treat a multi-session index change as a one-session return. Index turnover/costs are N/A. No alpha or same-feasible-set attribution. No external comparison is claimed if the gate fails.

## Verification and delivery

Test deterministic feasible targets, no look-ahead membership, selection changes including exits, next-close timing, held units, initial/terminal charge, hand-calculated metrics, paired bootstrap and C2 metadata/alignment fail-closed behavior. Reproduce C1 twice. Independently reconstruct units/NAV and B1/B2 metrics/costs; compare to frozen values. Hash existing inputs again after execution. Report adverse/null effects. Deliver readable Vietnamese report, figures/CSV, reproducibility manifest, separate C2 source decision and C3–C6 proposals. Create a new Drive folder under the user-designated reports parent if that session is accessible; never overwrite earlier reports or change sharing.
