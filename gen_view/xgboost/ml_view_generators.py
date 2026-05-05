"""
Backward-compatibility shim
==========================

The ML view generation logic has been centralized into ``view_generators.py``
and the ML predictor into ``view_ml/predictor.py``.
This module re-exports the public symbols so that any legacy imports of the form::

    from view_ml.ml_view_generators import TraditionalMLViewGenerator

continue to work without changes.
"""

# from xgboost.predictor import XGBoostReturnPredictor  # noqa: F401
# from view_generators import TraditionalMLViewGenerator, generate_ml_views  # noqa: F401

# __all__ = ["TraditionalMLViewGenerator", "XGBoostReturnPredictor", "generate_ml_views"]
