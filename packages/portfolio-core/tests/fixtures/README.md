# Synthetic numerical golden fixtures

These fixtures exercise the `0.1.0` public numerical contract with finite,
explicit daily-return inputs. Every asset, mean, covariance, market weight and
view is synthetic. No price dataset, trained model, live feed or legacy run
produced these inputs or expectations. `legacy_parity=false` is intentional.

Each JSON file contains `fixture_schema_version=1`, a stable ID, the core version
that introduced it, provenance, the complete allocation request, literal expected
numerical values and absolute tolerances. Expectations are analytical optima and
posterior values, not a recorded `allocate()` output. The source description and
derivation travel with the file when it is copied for installed-wheel testing.

| Case | Independent oracle and behavior covered |
| --- | --- |
| `ew_three_assets` | Exactly three equal weights; utility is `0.0011/3 - 0.000725/9`. Checks both defensive assets in the ordered result. |
| `mvo_daily_interior` | With risk aversion `2` and equity weight `x`, derivative is `0.0016 - 0.002x`, giving `(0.8, 0.2)` and utility `0.00064`. |
| `mvo_binding_group_and_cap` | In GOLD/EQUITY/BOND order, `(0.05, 0.4, 0.55)` saturates equity's group limit and bond's position cap. Marginal utilities there are `(0.00009, 0.00118, 0.00029)`, proving no feasible transfer improves the concave objective. |
| `bl_absolute_view` | Prior `(0.0005, 0.000125)` and unit-confidence view `0.001` give posterior `(0.00075, 0.000125)`. Using the original return covariance gives equity weight `0.825`, rather than optimizing against posterior mean uncertainty. |
| `bl_relative_correlated_view` | Relative view, nonzero cross-covariance and confidence `0.5` give `P A Pᵀ=0.000019`, `Omega=0.000038` and posterior difference `0.00058`. The equity optimum is exactly `33/38`; utility is `73/200000`. |

All covariance eigenvalues exceed the regularization floor, so these oracles do
not require a numerical eigensolver to derive the expected risk term. Existing
core tests separately cover regularization and invalid/infeasible inputs.

The suite compares EW weights to `1e-15`, optimized weights to `1e-7`, daily
objectives to `1e-11` (EW `1e-14`) and BL posterior entries to `1e-13`, with no
relative tolerance. These bounds allow small solver/linear-algebra drift while
detecting changed allocation or confidence semantics. Constraint residuals are
independently recomputed from the output and must be at most `1e-12`. The same
runtime also compares three complete JSON results exactly and checks that the
caller's request remains unchanged.

Run from the checkout:

```sh
python -m pytest packages/portfolio-core/tests -q
```

To check package isolation, from the repository root:

```sh
python -m pip install build
core_check_dir=$(mktemp -d)
python -m build --wheel --outdir "$core_check_dir/wheels" packages/portfolio-core
python -m venv "$core_check_dir/venv"
"$core_check_dir/venv/bin/python" -m pip install "$core_check_dir"/wheels/*.whl 'pytest>=8,<9'
cp -R packages/portfolio-core/tests "$core_check_dir/tests"
cd "$core_check_dir"
env -u PYTHONPATH "$core_check_dir/venv/bin/python" -I -c 'import pathlib, sys, portfolio_core; assert pathlib.Path(portfolio_core.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()); print(portfolio_core.__version__, portfolio_core.__file__)'
env -u PYTHONPATH "$core_check_dir/venv/bin/python" -I -m pytest tests -q
```

The fresh virtual environment has only the wheel's declared runtime dependencies
and pytest. Copying the tests avoids repository path injection; `-I` ignores
Python path configuration. The source-only legacy posterior comparison is
expected to skip here because the research source is absent. Golden comparisons,
constraint checks, deterministic calls and all other core tests still run.
The wheel intentionally contains runtime code, not research data or test assets.
