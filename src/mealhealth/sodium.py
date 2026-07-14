# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Vectorised numerical kernel for the sodium mediator.

This module is intentionally internal to the calculation engine for now: the
public sodium API remains gated on required external exposure and burden data.
The initial prototype represents usual SBP as normal with draw-specific mean
and SD.  The prepared-runtime boundary must be extended if the real-data review
selects another family or ensemble.  Keeping the numerical kernel separate lets
the mean-shift approximation, draw coherence, and runtime budget be validated
with synthetic inputs before any provisional data can leak into public results.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
import math

import numpy as np


@dataclass(frozen=True)
class SodiumRuntimeInputs:
    """Aligned primitive draws for one country's sodium calculation.

    Arrays use ``(draw, age, sex)`` unless documented otherwise.  SBP curves
    use a common exposure grid and have shape ``(draw, outcome, knot)``; their
    age attenuation has shape ``(outcome, age)``.  The stomach-cancer curve is
    age invariant and has shape ``(draw, knot)``.
    """

    baseline_urinary_g: np.ndarray
    sbp_mean_mmhg: np.ndarray
    sbp_sd_mmhg: np.ndarray
    recovery_fraction: np.ndarray
    sodium_tmrel_g: np.ndarray
    sodium_to_sbp_slope: np.ndarray
    sbp_curve_exposure_mmhg: np.ndarray
    sbp_curve_log_rr: np.ndarray
    sbp_age_attenuation: np.ndarray
    mediated_outcomes: tuple[str, ...]
    sodium_curve_exposure_g: np.ndarray
    stomach_curve_log_rr: np.ndarray

    def __post_init__(self) -> None:
        shape = self.baseline_urinary_g.shape
        if len(shape) != 3:
            raise ValueError("baseline_urinary_g must have shape (draw, age, sex)")
        if shape[2] != 2:
            raise ValueError("sodium inputs must contain exactly two sex strata")
        for name in ("sbp_mean_mmhg", "sbp_sd_mmhg"):
            value = np.asarray(getattr(self, name))
            if value.shape != shape:
                raise ValueError(f"{name} must have shape {shape}, got {value.shape}")

        draws, ages, _ = shape
        for name in (
            "recovery_fraction",
            "sodium_tmrel_g",
            "sodium_to_sbp_slope",
        ):
            value = np.asarray(getattr(self, name))
            if value.shape != (draws,):
                raise ValueError(
                    f"{name} must have shape ({draws},), got {value.shape}"
                )

        outcomes = len(self.mediated_outcomes)
        sbp_x = np.asarray(self.sbp_curve_exposure_mmhg)
        sbp_y = np.asarray(self.sbp_curve_log_rr)
        attenuation = np.asarray(self.sbp_age_attenuation)
        sodium_x = np.asarray(self.sodium_curve_exposure_g)
        stomach_y = np.asarray(self.stomach_curve_log_rr)
        if sbp_x.ndim != 1 or sbp_x.size < 2:
            raise ValueError("sbp_curve_exposure_mmhg must be a 1-D grid")
        if sbp_y.shape != (draws, outcomes, sbp_x.size):
            raise ValueError(
                "sbp_curve_log_rr must have shape "
                f"({draws}, {outcomes}, {sbp_x.size}), got {sbp_y.shape}"
            )
        if attenuation.shape != (outcomes, ages):
            raise ValueError(
                f"sbp_age_attenuation must have shape ({outcomes}, {ages}), "
                f"got {attenuation.shape}"
            )
        if sodium_x.ndim != 1 or sodium_x.size < 2:
            raise ValueError("sodium_curve_exposure_g must be a 1-D grid")
        if stomach_y.shape != (draws, sodium_x.size):
            raise ValueError(
                "stomach_curve_log_rr must have shape "
                f"({draws}, {sodium_x.size}), got {stomach_y.shape}"
            )

        arrays = (
            self.baseline_urinary_g,
            self.sbp_mean_mmhg,
            self.sbp_sd_mmhg,
            self.recovery_fraction,
            self.sodium_tmrel_g,
            self.sodium_to_sbp_slope,
            sbp_x,
            sbp_y,
            attenuation,
            sodium_x,
            stomach_y,
        )
        if not all(np.isfinite(np.asarray(value)).all() for value in arrays):
            raise ValueError("sodium runtime inputs must be finite")
        if not _strictly_increasing(sbp_x) or not _strictly_increasing(sodium_x):
            raise ValueError("relative-risk exposure grids must be strictly increasing")
        if (self.baseline_urinary_g < 0).any():
            raise ValueError("baseline urinary sodium must be non-negative")
        if (self.sbp_sd_mmhg <= 0).any():
            raise ValueError("SBP standard deviations must be positive")
        if ((self.recovery_fraction <= 0) | (self.recovery_fraction > 1)).any():
            raise ValueError("urinary recovery fractions must lie in (0, 1]")
        if (self.sodium_tmrel_g < 0).any():
            raise ValueError("sodium TMREL draws must be non-negative")
        if (self.sodium_to_sbp_slope <= 0).any():
            raise ValueError("sodium-to-SBP slopes must be positive")
        if (attenuation < 0).any():
            raise ValueError("SBP age attenuation must be non-negative")


@dataclass(frozen=True)
class SodiumRuntimeResult:
    """Draw-level outputs retained until the caller aggregates its estimand."""

    baseline_urinary_g: np.ndarray
    meal_urinary_g: np.ndarray
    baseline_effective_g: np.ndarray
    meal_effective_g: np.ndarray
    delta_sbp_mmhg: np.ndarray
    mediated_risk_ratio: np.ndarray
    stomach_risk_ratio: np.ndarray


@dataclass(frozen=True)
class PreparedSodiumRuntime:
    """Cached baseline integration for repeated meals in one country."""

    inputs: SodiumRuntimeInputs
    quadrature_order: int
    sbp_quadrature_mmhg: np.ndarray
    quadrature_weights: np.ndarray
    baseline_expected_sbp_rr: np.ndarray
    baseline_stomach_log_rr: np.ndarray


def evaluate_sodium_mean_shift(
    inputs: SodiumRuntimeInputs,
    *,
    baseline_scale: float,
    meal_sodium_g: float,
    quadrature_order: int = 20,
) -> SodiumRuntimeResult:
    """Evaluate coherent sodium risk-ratio draws for one country.

    ``meal_sodium_g`` is dietary elemental sodium.  The return arrays retain
    their draw dimension: mediated risk ratios have shape
    ``(draw, age, sex, outcome)`` and the stomach-cancer ratios have shape
    ``(draw, age, sex)``.  No means or quantiles are taken here.
    """

    prepared = prepare_sodium_runtime(inputs, quadrature_order=quadrature_order)
    return evaluate_prepared_sodium(
        prepared,
        baseline_scale=baseline_scale,
        meal_sodium_g=meal_sodium_g,
    )


def prepare_sodium_runtime(
    inputs: SodiumRuntimeInputs, *, quadrature_order: int = 20
) -> PreparedSodiumRuntime:
    """Integrate and cache fixed baseline risks for one country."""

    quadrature_order = _validate_quadrature_order(quadrature_order)
    u0 = np.asarray(inputs.baseline_urinary_g)
    nodes, weights = _normal_quadrature(quadrature_order, u0.dtype)
    sbp = (
        np.asarray(inputs.sbp_mean_mmhg)[..., None]
        + np.sqrt(np.asarray(2.0, dtype=u0.dtype))
        * np.asarray(inputs.sbp_sd_mmhg)[..., None]
        * nodes
    )
    sbp_curves = np.asarray(inputs.sbp_curve_log_rr)
    age_shape = np.asarray(inputs.sbp_age_attenuation).T[None, :, None, None, :]
    quadrature_weights = weights[None, None, None, :, None]
    base_log_rr = _interpolate_draw_outcome_curves(
        inputs.sbp_curve_exposure_mmhg, sbp_curves, sbp
    )
    base_expected_rr = np.sum(
        np.exp(base_log_rr * age_shape) * quadrature_weights, axis=-2
    )

    draw_axis = (slice(None), None, None)
    tmrel = np.asarray(inputs.sodium_tmrel_g)[draw_axis]
    u0_eff = np.maximum(u0, tmrel)
    base_stomach_log_rr = interpolate_draw_curves(
        inputs.sodium_curve_exposure_g,
        np.asarray(inputs.stomach_curve_log_rr),
        u0_eff,
    )
    return PreparedSodiumRuntime(
        inputs=inputs,
        quadrature_order=quadrature_order,
        sbp_quadrature_mmhg=sbp,
        quadrature_weights=quadrature_weights,
        baseline_expected_sbp_rr=base_expected_rr,
        baseline_stomach_log_rr=base_stomach_log_rr,
    )


def evaluate_prepared_sodium(
    prepared: PreparedSodiumRuntime,
    *,
    baseline_scale: float,
    meal_sodium_g: float,
) -> SodiumRuntimeResult:
    """Evaluate a meal using cached country baseline integrations."""

    inputs = prepared.inputs
    baseline_scale = float(baseline_scale)
    meal_sodium_g = float(meal_sodium_g)
    if not math.isfinite(baseline_scale) or not 0 <= baseline_scale <= 1:
        raise ValueError("baseline_scale must be finite and lie in [0, 1]")
    if not math.isfinite(meal_sodium_g) or meal_sodium_g < 0:
        raise ValueError("meal_sodium_g must be finite and non-negative")

    u0 = np.asarray(inputs.baseline_urinary_g)
    draw_axis = (slice(None), None, None)
    u1 = (
        baseline_scale * u0
        + np.asarray(inputs.recovery_fraction)[draw_axis] * meal_sodium_g
    )
    tmrel = np.asarray(inputs.sodium_tmrel_g)[draw_axis]
    u0_eff = np.maximum(u0, tmrel)
    u1_eff = np.maximum(u1, tmrel)
    delta_sbp = np.asarray(inputs.sodium_to_sbp_slope)[draw_axis] * (u1_eff - u0_eff)

    shifted_sbp = prepared.sbp_quadrature_mmhg + delta_sbp[..., None]

    sbp_curves = np.asarray(inputs.sbp_curve_log_rr)
    age_shape = np.asarray(inputs.sbp_age_attenuation).T[None, :, None, None, :]
    meal_log_rr = _interpolate_draw_outcome_curves(
        inputs.sbp_curve_exposure_mmhg, sbp_curves, shifted_sbp
    )
    meal_expected_rr = np.sum(
        np.exp(meal_log_rr * age_shape) * prepared.quadrature_weights, axis=-2
    )
    mediated = meal_expected_rr / prepared.baseline_expected_sbp_rr

    stomach_curves = np.asarray(inputs.stomach_curve_log_rr)
    meal_stomach_log_rr = interpolate_draw_curves(
        inputs.sodium_curve_exposure_g, stomach_curves, u1_eff
    )
    stomach = np.exp(meal_stomach_log_rr - prepared.baseline_stomach_log_rr)

    return SodiumRuntimeResult(
        baseline_urinary_g=u0,
        meal_urinary_g=u1,
        baseline_effective_g=u0_eff,
        meal_effective_g=u1_eff,
        delta_sbp_mmhg=delta_sbp,
        mediated_risk_ratio=mediated,
        stomach_risk_ratio=stomach,
    )


def interpolate_draw_curves(
    exposure_grid: np.ndarray,
    draw_log_rr: np.ndarray,
    exposure: np.ndarray,
) -> np.ndarray:
    """Linearly interpolate aligned draw curves and clamp outside their grid.

    ``draw_log_rr`` has shape ``(draw, knot)`` and ``exposure`` may have any
    shape whose first dimension is the same draw dimension.  This implements
    the existing engine's log-linear RR interpolation without a Python draw
    loop.
    """

    y = np.asarray(draw_log_rr)
    if y.ndim != 2:
        raise ValueError("draw_log_rr must have shape (draw, exposure_grid.size)")
    return _interpolate_draw_outcome_curves(exposure_grid, y[:, None, :], exposure)[
        ..., 0
    ]


def _interpolate_draw_outcome_curves(
    exposure_grid: np.ndarray,
    draw_outcome_log_rr: np.ndarray,
    exposure: np.ndarray,
) -> np.ndarray:
    """Interpolate curves shaped ``(draw, outcome, knot)`` in one batch."""

    x = np.asarray(exposure_grid)
    y = np.asarray(draw_outcome_log_rr)
    values = np.asarray(exposure)
    if x.ndim != 1 or x.size < 2 or not _strictly_increasing(x):
        raise ValueError("exposure_grid must be a strictly increasing 1-D grid")
    if y.ndim != 3 or y.shape[2] != x.size:
        raise ValueError(
            "draw_outcome_log_rr must have shape (draw, outcome, exposure_grid.size)"
        )
    if values.ndim < 1 or values.shape[0] != y.shape[0]:
        raise ValueError("exposure and curve arrays must share their draw dimension")
    if not np.isfinite(values).all() or not np.isfinite(y).all():
        raise ValueError("curve values and evaluated exposures must be finite")

    interval = np.searchsorted(x, values, side="right") - 1
    interval = np.clip(interval, 0, x.size - 2)
    curve_shape = (y.shape[0],) + (1,) * (values.ndim - 1) + (y.shape[1], x.size)
    curves = y.reshape(curve_shape)
    take = interval[..., None, None]
    y0 = np.take_along_axis(curves, take, axis=-1)[..., 0]
    y1 = np.take_along_axis(curves, take + 1, axis=-1)[..., 0]
    x0 = x[interval][..., None]
    x1 = x[interval + 1][..., None]
    out = y0 + (values[..., None] - x0) / (x1 - x0) * (y1 - y0)

    edge_shape = (y.shape[0],) + (1,) * (values.ndim - 1) + (y.shape[1],)
    low = y[:, :, 0].reshape(edge_shape)
    high = y[:, :, -1].reshape(edge_shape)
    return np.where(
        values[..., None] <= x[0],
        low,
        np.where(values[..., None] >= x[-1], high, out),
    )


def _strictly_increasing(values: np.ndarray) -> bool:
    return bool(np.all(np.diff(values) > 0))


def _validate_quadrature_order(order: int) -> int:
    if isinstance(order, bool) or not isinstance(order, (int, np.integer)):
        raise ValueError("quadrature_order must be an integer")
    if order < 2:
        raise ValueError("quadrature_order must be at least 2")
    return int(order)


@cache
def _normal_quadrature(order: int, dtype: np.dtype) -> tuple[np.ndarray, np.ndarray]:
    nodes, weights = np.polynomial.hermite.hermgauss(order)
    dtype = np.dtype(dtype)
    nodes = nodes.astype(dtype, copy=False)
    weights = (weights / np.sqrt(np.pi)).astype(dtype, copy=False)
    return nodes, weights
