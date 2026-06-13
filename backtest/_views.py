"""Dynamic view generation dispatch.

Routes to the correct view generator based on the selected mode
(rule_based, relative, ml, combined).
"""

import pandas as pd

from config import COMBINED_VIEW_WEIGHTS, ML_MIN_RETURN_THRESHOLD, VIEW_MODE
from gen_view.view_generators import (
    build_views_matrix,
    combine_views,
    generate_ml_views,
    generate_relative_views,
    generate_rule_based_views,
    generate_static_views,
)


def generate_dynamic_views(
    price_window: pd.DataFrame,
    assets: list,
    mode: str = VIEW_MODE,
    ml_model=None,
    ml_min_return_threshold: float = ML_MIN_RETURN_THRESHOLD,
):
    """Generate views dynamically based on the selected mode.

    Parameters
    ----------
    price_window : pd.DataFrame
        Price data for the lookback window (used for indicator calculation).
    assets : list
        List of asset names.
    mode : str
        View generation mode: ``"rule_based"``, ``"relative"``, ``"ml"``, ``"combined"``.
    ml_model : XGBoostCoreModel, optional
        Trained ML model (used when mode is ``"ml"`` or ``"combined"``).
    ml_min_return_threshold : float
        Minimum predicted return to generate a view.

    Returns
    -------
    tuple
        ``(P matrix, Q vector, confidence vector, view names)``
    """
    views = []

    if mode == "rule_based":
        views = generate_rule_based_views(price_window)
    elif mode == "relative":
        views = generate_relative_views(price_window)
    elif mode == "ml":
        if ml_model is None:
            return None, None, None, []
        predictions = ml_model.predict(price_window)
        views = generate_ml_views(
            predictions,
            prediction_horizon=ml_model.prediction_horizon,
            min_return_threshold=ml_min_return_threshold,
        )
    elif mode == "combined":
        rule_views = generate_rule_based_views(price_window)
        rel_views = generate_relative_views(price_window)
        static_views = generate_static_views()
        if ml_model is not None:
            predictions = ml_model.predict(price_window)
            ml_views = generate_ml_views(
                predictions,
                prediction_horizon=ml_model.prediction_horizon,
                min_return_threshold=ml_min_return_threshold,
            )
        else:
            ml_views = []
        views = combine_views(
            rule_views, rel_views, ml_views, static_views, COMBINED_VIEW_WEIGHTS
        )

    return build_views_matrix(views, assets)
