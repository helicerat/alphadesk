"""Reusable validation window.

Thresholdout, from Dwork, Feldman, Hardt, Pitassi, Reingold, Roth,
"The reusable holdout: Preserving validity in adaptive data analysis",
Science 349(6248):636-638, 2015.

If the validation value is close to the development value, the agent gets
the development value back and learns nothing new about the validation
window. Only when they disagree by more than a noisy threshold does it get a
noisy validation value. That is what lets agents ask the validation window
many times without turning it into training data.
"""

from __future__ import annotations

import numpy as np


class Thresholdout:
    def __init__(self, threshold: float = 0.01, sigma: float = 0.004, budget: int = 200, seed: int = 0):
        self.threshold = threshold
        self.sigma = sigma
        self.budget = budget
        self.rng = np.random.default_rng(seed)
        self.used = 0
        self._t_hat = threshold + self.rng.laplace(scale=2 * sigma)

    def query(self, dev_value: float, valid_value: float) -> dict:
        if not (np.isfinite(dev_value) and np.isfinite(valid_value)):
            return {"value": float("nan"), "overfit_flag": False, "budget_left": self.budget}
        if self.budget <= 0:
            return {"value": float(dev_value), "overfit_flag": False, "budget_left": 0, "exhausted": True}
        gap = abs(dev_value - valid_value)
        if gap > self._t_hat + self.rng.laplace(scale=4 * self.sigma):
            self.budget -= 1
            self.used += 1
            self._t_hat = self.threshold + self.rng.laplace(scale=2 * self.sigma)
            return {"value": float(valid_value + self.rng.laplace(scale=self.sigma)),
                    "overfit_flag": True, "budget_left": self.budget}
        return {"value": float(dev_value), "overfit_flag": False, "budget_left": self.budget}
