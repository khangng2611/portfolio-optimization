# Independent review

Reviewed by the review_core_method agent on 2026-10-23 under the portfolio-research-audit and requesting-code-review workflows. Read-only review of core.py, frozen.py, run.py, tests and final report against guide_1.md/project_1.md and primary CSVs.

No Critical or Important numerical/timing defect found. Confirmed next-close execution, fixed-share continuity across IS/OOS, selection t−1 cutoff, covariance timing, prior-only empty views, paired bootstrap and execution-day per-side costs. Reconstructed regularized covariance matches all 293 saved BL samples to a maximum 2.60e-18; all saved Q/confidence records match views_history. Six core unit tests passed.

Report tables, effect sizes, structural summaries, 7-of-10 random comparison, HHI/effective holdings, cost crossover and bootstrap intervals reconcile. H1–H6 verdicts are appropriately conditional.

Resolved documentation findings:

- Exact supplied-guide copies, exported Step1 Google Docs report and implementation plan are hashed in the publication evidence manifest, explicitly distinguished from the pre-execution numerical freeze.
- The report opening now specifies gross OOS ML improvement. IS reversal is explicitly stated (B2 Sharpe 0.614 vs B1 0.794), alongside the complete IS table.

Declared limitations remain: static universe, assumed historical availability, unverified adjusted-price vintage, valuation proxies for GOLD/VFF, approximate costs, analytical daily random-median stream, and skipped standalone confidence/regime tests.
