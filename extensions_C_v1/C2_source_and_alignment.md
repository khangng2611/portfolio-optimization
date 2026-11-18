# C2 source and alignment status

NOT RUN: source gate not met. Candidate VN30TRI; expected anchor 2023-09-29, 641 portfolio returns 2023-10-02–2026-04-29. Accepted source level rows: 0; aligned returns: 0. All 641 dates are not evaluable because no accepted series was supplied, not because verified market observations are missing on those dates. See C2_unmatched_dates.csv. No interpolation, zero filling or replacement with VNINDEX price return. C2_results.csv is a status row with null metrics; C2_market_daily.csv contains a header only.

Identity and gross dividend-reinvestment definition verified from HOSE/SSC documentation; daily level file, vendor_record_date, complete historical vintage/change record and explicit research-use evidence remain absent. See C2_source_feasibility.md and C2_source_audit.json for source URLs and findings.

Future approved input: C2_market.py checks metadata, freezes local inputs/hashes before calculation, rejects duplicate/nonpositive/unsorted observations, never bridges a missing session, and chooses the longest contiguous daily common sample (earliest tie). B1/B2 are recomputed and all three paths re-anchored on the same prior session. Index turnover is N/A; gross index is descriptive, not an executable same-constraint benchmark.
