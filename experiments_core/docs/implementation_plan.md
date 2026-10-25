# Core Evidence Sprint Implementation Plan

**Goal:** Execute the supplied guide_1.md and project_1.md, report Step 2 in Vietnamese, and submit the report and evidence to the user-specified Drive folder.

**Architecture:** A small isolated experiment package imports numerical functions from the immutable 12/10 candidate workspace. Reuse recorded causal selections and ML views, verify their provenance, reconstruct the baseline holdings path, and solve new matched allocations. Existing research/application code and all Step 1 artifacts remain unchanged.

**Specification:** `/Users/nguyenkhang/Documents/MASTER/Thesis/phase2-journal-plan/guide_1.md` and `project_1.md` (their internal names still say guide_0/project_0).

**Constraints:** K=5; random seeds 7,11,19,23,31,43,59,71,83,97; bootstrap moving blocks 10 sessions, 1000 replicates, seed 20261014; costs 0/10/25/50 bps per side; 641 OOS returns; same information policy and next-close execution; no OOS tuning.

## Decisions made for implementation

- Reuse the current checkout with a new `codex/core-evidence-sprint` branch; new files only in experiments_core. The checkout contains ignored research inputs unavailable in a clean worktree.
- A and B use fixed risk aversion 1.5, the frozen feasible set, no defensive regime views, and no Hybrid. B2 reuses saved ML P/Q/confidences (including the frozen volatility confidence dampener), removing defensive views. This intentional controlled variant is not asserted identical to legacy BL.
- At the first IS selection event there are only 19 prior returns. All arms share this initial eligibility; Simple uses the available 19, then exactly 20. This preserves the baseline selection and execution calendars; no effect on the OOS warmup length.
- Baseline verification is an independent saved-decision replay and metric/input reconciliation, not another ML fit. The two preserved fresh-fit baseline runs are also compared by hashes.
- Optional mechanism probes are skipped. H4/H5 remain untested by this sprint.
- User already requested implementation and Drive submission; proceed with routine reversible choices under that authorization. No extra design approval gate is introduced.

## Tasks and verification

- [ ] 1. Freeze source, data, config, seeds, original docs and Step 1 report; write manifest before execution. Verify baseline hashes, saved-decision replay, OOS metrics and constraints.
- [ ] 2. Test and implement next-close fixed-share simulation, BL prior-only case, historical Simple selection, paired bootstrap and cost accounting. Run unit tests before full experiment.
- [ ] 3. Run A0/A2/A3 and ten random full paths; B0/B1/B2 on identical selected universes. Save returns, target and daily holdings, turnover, selection matrices/history, posterior audit, source/config/environment provenance and registry.
- [ ] 4. Re-execute deterministic allocations and paths; audit availability, selection history, scaler/labels, timing, constraints, compounding, units, and metrics. Calculate cost sensitivity and paired bootstrap intervals; generate figures.
- [ ] 5. Write Vietnamese report, paper-revision handoff, attachment index and portable evidence archive. Verify report/figures and upload to the requested folder; verify remote presence.

## Review focus

Execution-day returns belong to old holdings; costs use execution date, including final-close trades. IS/OOS normalization never resets holdings. GOLD belongs to the non-VFF group, making VFF's effective floor 30%. Empty views mean BL prior, never sample mean. Random aggregate is the cross-seed median each date, a descriptive analytical stream.

## Progress

2026-10-23: Read the supplied guides, active baseline, frozen numerical implementation, readiness checks and exported Google Docs report. Found relocation of historical absolute paths; map them to the current repository and verify content hashes rather than altering old manifests.
