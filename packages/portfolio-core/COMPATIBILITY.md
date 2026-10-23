# Compatibility and versioning

`portfolio-core` is versioned independently of the web application, API contracts,
Portfolio, Quant and Market Data services. Its distribution version, exported
`portfolio_core.__version__` and result `core_version` identify the numerical
implementation. Consumers should pin the exact core and runtime dependency
versions when comparing allocations or recording experiment provenance.

## Numerical contract

The public contract is `allocate(request: dict) -> dict`, `CoreError`, the
documented input units/shapes, strategies, constraint semantics, result ordering,
diagnostics and machine-readable error codes. A caller must supply the asset
universe in order, compatible daily data, every policy field and prepared BL
views. It must also record the data cutoff, immutable input/snapshot reference,
model/view provenance where applicable, core version and dependency lock.

Repeated calls with identical inputs in the pinned runtime must produce
repeatable results. Across CPU, BLAS and operating-system versions, numerical
equivalence is assessed with declared fixture tolerances. Bitwise identity across
platforms and all historical dependency versions is not promised.

While the package is `0.x`, apply these rules:

| Change | Release treatment |
| --- | --- |
| Documentation, new independent fixtures or test-only verification | No numerical version bump required; record under Unreleased. |
| Compatible bug fix restoring the documented numerical contract | Patch bump, failing regression test, changelog entry and comparison against existing fixtures. |
| New strategy/input capability, changed dependencies/solver defaults, changed numerical convention, validation acceptance or allocation behavior | Minor bump; document affected inputs, before/after behavior and migration. |
| Removed/renamed inputs, strategies, fields or error codes | Minor bump during `0.x`, with an explicit breaking-change notice; major bump once stable `1.x`. |

Any dependency update requires fixture verification, including an installed-wheel
run; dependency pins are part of numerical provenance. A change that intentionally
invalidates an established numerical fixture must be explained and versioned.
Do not overwrite expected values by regenerating them from the implementation.
For `1.x`, backward-incompatible public changes require a major version bump.

Authentication, idempotency, ownership, persistence, HTTP validation or application
workflow fixes belong to the application/service contract and changelog. They do
not require a core version bump unless they also change the numerical package.
Application releases must still expose or persist the core version used by each
allocation so an API version cannot be mistaken for a numerical version.

## Phase 1 research preservation

The preserved Phase 1/legacy pipeline and its recorded evidence are a separate
research baseline. Application correctness fixes do not authorize rewriting that
baseline, replacing its outputs, rerunning it under silent policy changes or
claiming improved research performance. A research rerun needs explicit
configuration, data/model/result provenance and separately labeled evidence.

The core preserves the documented BL posterior formula and covariance eigenvalue
floor for explicit inputs. It deliberately rejects invalid data and solver
failures, enforces final constraints and retains small feasible positions rather
than using legacy fallback, clipping, threshold and redistribution behavior.
Consequently, formula checks and synthetic fixtures establish only the stated
numerical contracts for their inputs. They do not establish parity of legacy
rankings, universe selection, preprocessing, trained XGBoost views, regimes,
rebalancing, backtests, metrics or live market ingestion. `BL_ML` accepts prepared
views; no model inference occurs inside this package.

## Golden fixture evidence

The versioned JSON format and independent derivations are described in
[tests/fixtures/README.md](tests/fixtures/README.md). These cases are synthetic;
their provenance explicitly records `legacy_parity=false` and no market data or
trained model. They remain useful even when the legacy source is absent.

Keep all existing golden cases when adding behavior. Add a new fixture with
reviewable derivation and explicit tolerances for an intentional extension. A
legacy-parity fixture would additionally need immutable legacy source/config,
data and model identities, the legacy output, and a reproducible comparison;
the current synthetic cases cannot be relabeled as that evidence.

Before a numerical release, run the entire core suite, the backend consumer
suite, and the same core tests copied outside the checkout against a fresh wheel
installation. Report any source-only legacy comparison skipped in the external
run. Solver weights/objectives may use numerical tolerances; returned constraints
must still meet the documented `1e-12` final residual bound.
