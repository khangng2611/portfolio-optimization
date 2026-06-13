"""Black-Litterman posterior expected returns calculation."""

import numpy as np

from config import BL_DELTA, BL_TAU

from backtest._optimizer import _regularize_covariance


def black_litterman_posterior_mu(
    sigma,
    market_weights,
    p,
    q,
    confidences,
    tau=BL_TAU,
    delta=BL_DELTA,
):
    """Compute Black-Litterman posterior expected returns.

    Parameters
    ----------
    sigma : array-like, shape (n, n)
        Asset return covariance matrix.
    market_weights : array-like, shape (n,)
        Market equilibrium weights (used to derive implied returns π).
    p : array-like, shape (k, n)
        View pick matrix (k views over n assets).
    q : array-like, shape (k,)
        View expected returns.
    confidences : array-like, shape (k,)
        View confidences in [0, 1].
    tau : float
        Uncertainty scalar for the prior.
    delta : float
        Risk-aversion parameter used to derive π = δ·Σ·w_mkt.
    """
    sigma = _regularize_covariance(sigma)
    market_weights = np.asarray(market_weights, dtype=float)
    p = np.asarray(p, dtype=float)
    q = np.asarray(q, dtype=float)
    confidences = np.clip(np.asarray(confidences, dtype=float), 1e-6, 1.0)

    pi = delta * sigma @ market_weights
    omega_diag = np.diag(p @ (tau * sigma) @ p.T)
    omega_diag = np.clip(omega_diag, 1e-10, None)
    omega = np.diag(omega_diag / confidences)

    inv_tau_sigma = np.linalg.inv(tau * sigma)
    inv_omega = np.linalg.inv(omega)

    middle = inv_tau_sigma + p.T @ inv_omega @ p
    rhs = inv_tau_sigma @ pi + p.T @ inv_omega @ q
    return np.linalg.solve(middle, rhs)
