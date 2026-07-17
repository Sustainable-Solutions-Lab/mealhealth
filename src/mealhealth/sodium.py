# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Deterministic country-age-sex mean-shift model for sodium."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import data

# Central values pinned and validated against tools/reference/sodium_to_sbp.json.
# The runtime reports no sodium uncertainty interval.
SODIUM_URINARY_RECOVERY = 0.928
SODIUM_TMREL_LOW_G_PER_DAY = 1.0
SODIUM_TMREL_HIGH_G_PER_DAY = 5.0
SODIUM_TMREL_CENTRAL_G_PER_DAY = 3.0
SODIUM_TO_SBP_MMHG_PER_G = 2.42

# GBD's sodium TMREL is an interval, not a point estimate. The integral over
# Uniform(1, 5) is split at each exposure's clipping point and evaluated with
# deterministic Gauss-Legendre quadrature. Splitting removes quadrature error
# at the ``max`` kinks without introducing stochastic noise.
_TMREL_QUADRATURE_NODES, _TMREL_QUADRATURE_WEIGHTS = np.polynomial.legendre.leggauss(12)

MEDIATED_CURVE_BY_CAUSE = {
    "CHD": "CHD",
    "Stroke": "Stroke",
    "HaemorrhagicStroke": "Stroke",
    "CKD": "CKD",
}


@dataclass(frozen=True)
class SodiumStratumEffect:
    """Central mean-shift result for one country-age-sex stratum."""

    baseline_urinary_g: float
    meal_urinary_g: float
    baseline_effective_g: float
    meal_effective_g: float
    delta_sbp_mmhg: float
    risk_ratio: float


class SodiumMeanShiftModel:
    """Deterministic central sodium mean-shift model.

    This is a mean-field approximation: each stratum is represented by its GBD
    mean urinary sodium and mean SBP. It does not reconstruct the distribution
    of either exposure between people. See ``docs/methodology.md``.
    """

    def __init__(self, country: str):
        mediator = data.baseline_mediators()
        mediator = mediator[mediator["country"] == country]
        if mediator.empty:
            raise KeyError(f"No bundled sodium mediator baseline for {country!r}")
        self.country = country
        self.baseline_urinary_g = {
            (row.age, row.sex): float(row.sodium_urinary_g_per_day_mean)
            for row in mediator.itertuples(index=False)
        }
        self.baseline_sbp_mmhg = {
            (row.age, row.sex): float(row.sbp_mmhg_mean)
            for row in mediator.itertuples(index=False)
        }

        curves = data.sodium_relative_risks()
        self.curves: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
        for (path, cause), group in curves.groupby(["path", "curve_cause"], sort=False):
            self.curves[(str(path), str(cause))] = (
                group["exposure"].to_numpy(dtype=float),
                np.log(group["rr_mean"].to_numpy(dtype=float)),
            )
        attenuation = data.sbp_age_attenuation()
        self.age_attenuation = {
            (row.curve_cause, row.age): float(row.beta)
            for row in attenuation.itertuples(index=False)
        }

    def urinary_exposure(
        self, age: str, sex: str, *, baseline_scale: float, meal_sodium_g: float
    ) -> tuple[float, float]:
        """Return baseline and substituted urinary sodium in g/day."""

        baseline = self.baseline_urinary_g[(age, sex)]
        meal = baseline_scale * baseline + SODIUM_URINARY_RECOVERY * meal_sodium_g
        return baseline, meal

    def stratum_effect(
        self,
        cause: str,
        age: str,
        sex: str,
        *,
        baseline_scale: float,
        meal_sodium_g: float,
    ) -> SodiumStratumEffect:
        """Evaluate the central sodium risk ratio for one burden cause."""

        baseline, meal = self.urinary_exposure(
            age, sex, baseline_scale=baseline_scale, meal_sodium_g=meal_sodium_g
        )
        # Scalar effective values are diagnostic midpoints. Risk itself is
        # averaged over the full uniform TMREL interval below.
        baseline_effective = max(baseline, SODIUM_TMREL_CENTRAL_G_PER_DAY)
        meal_effective = max(meal, SODIUM_TMREL_CENTRAL_G_PER_DAY)
        if meal == baseline:
            return SodiumStratumEffect(
                baseline, meal, baseline_effective, meal_effective, 0.0, 1.0
            )

        tmrel, expectation_weights = _tmrel_quadrature(baseline, meal)
        baseline_effective_nodes = np.maximum(baseline, tmrel)
        meal_effective_nodes = np.maximum(meal, tmrel)

        if cause == "StomachCancer":
            base_log_rr = self._log_rr_array(
                "sodium", "StomachCancer", baseline_effective_nodes
            )
            meal_log_rr = self._log_rr_array(
                "sodium", "StomachCancer", meal_effective_nodes
            )
            delta_sbp = 0.0
        else:
            curve_cause = MEDIATED_CURVE_BY_CAUSE.get(cause)
            if curve_cause is None:
                return SodiumStratumEffect(
                    baseline, meal, baseline_effective, meal_effective, 0.0, 1.0
                )
            delta_sbp_nodes = SODIUM_TO_SBP_MMHG_PER_G * (
                meal_effective_nodes - baseline_effective_nodes
            )
            delta_sbp = SODIUM_TO_SBP_MMHG_PER_G * (meal_effective - baseline_effective)
            baseline_sbp = self.baseline_sbp_mmhg[(age, sex)]
            beta = self.age_attenuation[(curve_cause, age)]
            base_log_rr = beta * self._log_rr_array(
                "sbp", curve_cause, np.full_like(delta_sbp_nodes, baseline_sbp)
            )
            meal_log_rr = beta * self._log_rr_array(
                "sbp", curve_cause, baseline_sbp + delta_sbp_nodes
            )

        risk_ratio = float(
            np.dot(expectation_weights, np.exp(meal_log_rr - base_log_rr))
        )
        return SodiumStratumEffect(
            baseline,
            meal,
            baseline_effective,
            meal_effective,
            delta_sbp,
            risk_ratio,
        )

    def weighted_exposure(
        self,
        population: dict[tuple[str, str], float],
        *,
        baseline_scale: float,
        meal_sodium_g: float,
    ) -> tuple[float, float]:
        """Adult-population weighted baseline and substituted urinary means."""

        baseline_total = 0.0
        meal_total = 0.0
        weight_total = 0.0
        for (age, sex), baseline in self.baseline_urinary_g.items():
            weight = population.get((sex, age), 0.0)
            meal = baseline_scale * baseline + SODIUM_URINARY_RECOVERY * meal_sodium_g
            baseline_total += weight * baseline
            meal_total += weight * meal
            weight_total += weight
        if weight_total <= 0:
            raise ValueError(f"No adult population weights for {self.country}")
        return baseline_total / weight_total, meal_total / weight_total

    def _log_rr_array(
        self, path: str, curve_cause: str, exposure: np.ndarray
    ) -> np.ndarray:
        x, log_rr = self.curves[(path, curve_cause)]
        return np.interp(exposure, x, log_rr)


def _tmrel_quadrature(*breakpoints: float) -> tuple[np.ndarray, np.ndarray]:
    """Return nodes and expectation weights for the uniform sodium TMREL."""

    bounds = {
        SODIUM_TMREL_LOW_G_PER_DAY,
        SODIUM_TMREL_HIGH_G_PER_DAY,
        *(
            point
            for point in breakpoints
            if SODIUM_TMREL_LOW_G_PER_DAY < point < SODIUM_TMREL_HIGH_G_PER_DAY
        ),
    }
    ordered = sorted(bounds)
    nodes = []
    weights = []
    tmrel_width = SODIUM_TMREL_HIGH_G_PER_DAY - SODIUM_TMREL_LOW_G_PER_DAY
    for low, high in zip(ordered[:-1], ordered[1:], strict=True):
        midpoint = (low + high) / 2.0
        half_width = (high - low) / 2.0
        nodes.append(midpoint + half_width * _TMREL_QUADRATURE_NODES)
        weights.append(_TMREL_QUADRATURE_WEIGHTS * half_width / tmrel_width)
    return np.concatenate(nodes), np.concatenate(weights)
