# Changelog

Changes to the numerical package are recorded separately from application and
service releases. See [compatibility policy](COMPATIBILITY.md).

## Unreleased

### Added

- Five synthetic JSON golden fixtures for EW, daily-unit MVO, MVO with binding
  group and position limits, and BL allocations from absolute and correlated
  relative views. Expected values are derived analytically, independently of
  `portfolio_core.allocate`.
- Checks for numerical tolerances, constraints recomputed from returned weights,
  repeatability, finite JSON output and input immutability. Tests can run against
  a wheel installed outside the research checkout.
- Compatibility, fixture provenance and release guidance.

No numerical behavior or public API changed in this work. The package remains
`0.1.0`; these fixtures do not establish end-to-end legacy or trained-model parity.

## 0.1.0

Initial separated explicit-input numerical API:

- `allocate(request)` and structured `CoreError` failures for EW, MVO and BL_ML.
- Ordered daily-return arrays, explicit per-request policies and covariance
  validation/regularization without research imports, training or data fetching.
- Constrained CLARABEL optimization, finite output validation and feasibility
  correction limited to numerical drift.
- Prepared Black–Litterman views with the documented legacy posterior confidence
  convention; the allocation risk term uses regularized return covariance.

The solver, failure and feasibility behavior intentionally differs from legacy
fallbacks, clipping, small-position removal and redistribution. This release is
an application numerical contract, not a reproduction of the Phase 1 pipeline.
