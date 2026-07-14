# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the draw-preserving sodium mean-shift numerical kernel."""

from dataclasses import replace

import numpy as np
import pytest

from mealhealth.sodium import (
    SodiumRuntimeInputs,
    evaluate_prepared_sodium,
    evaluate_sodium_mean_shift,
    interpolate_draw_curves,
    prepare_sodium_runtime,
)


def _linear_inputs() -> SodiumRuntimeInputs:
    draws, ages, sexes = 3, 2, 2
    u0 = np.array(
        [
            [[2.0, 3.0], [4.0, 5.0]],
            [[2.5, 3.5], [4.5, 5.5]],
            [[3.0, 4.0], [5.0, 6.0]],
        ]
    )
    sbp_mean = np.full((draws, ages, sexes), 130.0)
    sbp_sd = np.full((draws, ages, sexes), 10.0)
    sbp_x = np.linspace(0.0, 300.0, 31)
    sbp_log_rr = np.empty((draws, 1, sbp_x.size))
    for draw, coefficient in enumerate((0.01, 0.02, 0.03)):
        sbp_log_rr[draw, 0] = coefficient * sbp_x
    sodium_x = np.linspace(0.0, 10.0, 11)
    stomach_log_rr = np.array(
        [coefficient * sodium_x for coefficient in (0.1, 0.2, 0.3)]
    )
    return SodiumRuntimeInputs(
        baseline_urinary_g=u0,
        sbp_mean_mmhg=sbp_mean,
        sbp_sd_mmhg=sbp_sd,
        recovery_fraction=np.array([0.90, 0.95, 1.00]),
        sodium_tmrel_g=np.array([1.0, 3.0, 5.0]),
        sodium_to_sbp_slope=np.array([1.0, 2.0, 3.0]),
        sbp_curve_exposure_mmhg=sbp_x,
        sbp_curve_log_rr=sbp_log_rr,
        sbp_age_attenuation=np.array([[1.0, 0.5]]),
        mediated_outcomes=("synthetic_cardiovascular",),
        sodium_curve_exposure_g=sodium_x,
        stomach_curve_log_rr=stomach_log_rr,
    )


def _trapezoid(values: np.ndarray, grid: np.ndarray) -> float:
    return float(np.sum((values[:-1] + values[1:]) * np.diff(grid) / 2.0))


def test_interpolate_draw_curves_matches_independent_numpy_calls():
    x = np.array([0.0, 1.0, 3.0])
    y = np.array([[0.0, 1.0, 2.0], [10.0, 12.0, 16.0]])
    values = np.array([[[-1.0, 0.5, 2.0, 4.0]], [[-1.0, 0.5, 2.0, 4.0]]])
    actual = interpolate_draw_curves(x, y, values)
    expected = np.stack(
        [np.interp(values[draw], x, y[draw]) for draw in range(y.shape[0])]
    )
    assert actual == pytest.approx(expected)


def test_tmrel_clipping_and_conversion_are_applied_draw_by_draw():
    inputs = _linear_inputs()
    result = evaluate_sodium_mean_shift(inputs, baseline_scale=0.5, meal_sodium_g=1.0)
    expected_u1 = (
        0.5 * inputs.baseline_urinary_g + np.array([0.90, 0.95, 1.00])[:, None, None]
    )
    expected_u0_eff = np.maximum(
        inputs.baseline_urinary_g, np.array([1.0, 3.0, 5.0])[:, None, None]
    )
    expected_u1_eff = np.maximum(expected_u1, np.array([1.0, 3.0, 5.0])[:, None, None])
    expected_delta = np.array([1.0, 2.0, 3.0])[:, None, None] * (
        expected_u1_eff - expected_u0_eff
    )
    assert result.meal_urinary_g == pytest.approx(expected_u1)
    assert result.baseline_effective_g == pytest.approx(expected_u0_eff)
    assert result.meal_effective_g == pytest.approx(expected_u1_eff)
    assert result.delta_sbp_mmhg == pytest.approx(expected_delta)


def test_linear_log_rr_curves_have_closed_form_risk_ratios():
    inputs = _linear_inputs()
    result = evaluate_sodium_mean_shift(
        inputs, baseline_scale=0.5, meal_sodium_g=1.0, quadrature_order=12
    )
    sbp_coefficients = np.array([0.01, 0.02, 0.03])[:, None, None]
    expected_first_age = np.exp(sbp_coefficients * result.delta_sbp_mmhg)
    expected_second_age = np.exp(0.5 * sbp_coefficients * result.delta_sbp_mmhg)
    assert result.mediated_risk_ratio[:, 0, :, 0] == pytest.approx(
        expected_first_age[:, 0, :]
    )
    assert result.mediated_risk_ratio[:, 1, :, 0] == pytest.approx(
        expected_second_age[:, 1, :]
    )

    stomach_coefficients = np.array([0.1, 0.2, 0.3])[:, None, None]
    expected_stomach = np.exp(
        stomach_coefficients * (result.meal_effective_g - result.baseline_effective_g)
    )
    assert result.stomach_risk_ratio == pytest.approx(expected_stomach)


def test_identity_intervention_is_exactly_one():
    inputs = _linear_inputs()
    # With recovery=1 and meal=(1-f)*u0, identity cannot hold for all strata.
    # Use a constant baseline to exercise an exact identity in every draw.
    constant_u0 = np.full_like(inputs.baseline_urinary_g, 4.0)
    identity = replace(
        inputs,
        baseline_urinary_g=constant_u0,
        recovery_fraction=np.ones(3),
        sodium_tmrel_g=np.ones(3),
    )
    result = evaluate_sodium_mean_shift(
        identity, baseline_scale=0.75, meal_sodium_g=1.0
    )
    assert np.array_equal(result.meal_urinary_g, constant_u0)
    assert np.array_equal(result.delta_sbp_mmhg, np.zeros_like(constant_u0))
    assert result.mediated_risk_ratio == pytest.approx(1.0)
    assert result.stomach_risk_ratio == pytest.approx(1.0)


def test_prepared_runtime_exactly_matches_one_shot_evaluation():
    inputs = _linear_inputs()
    one_shot = evaluate_sodium_mean_shift(
        inputs, baseline_scale=0.6, meal_sodium_g=1.2, quadrature_order=16
    )
    prepared = prepare_sodium_runtime(inputs, quadrature_order=16)
    cached = evaluate_prepared_sodium(prepared, baseline_scale=0.6, meal_sodium_g=1.2)
    assert np.array_equal(cached.mediated_risk_ratio, one_shot.mediated_risk_ratio)
    assert np.array_equal(cached.stomach_risk_ratio, one_shot.stomach_risk_ratio)
    assert np.array_equal(cached.delta_sbp_mmhg, one_shot.delta_sbp_mmhg)


def test_gaussian_quadrature_matches_dense_grid_for_nonlinear_curve():
    inputs = _linear_inputs()
    sbp_x = np.linspace(80.0, 200.0, 49)
    nonlinear = 0.002 * np.maximum(sbp_x - 110.0, 0.0) ** 1.35
    one = SodiumRuntimeInputs(
        baseline_urinary_g=np.array([[[4.0, 4.0]]]),
        sbp_mean_mmhg=np.array([[[132.0, 132.0]]]),
        sbp_sd_mmhg=np.array([[[13.0, 13.0]]]),
        recovery_fraction=np.array([1.0]),
        sodium_tmrel_g=np.array([1.0]),
        sodium_to_sbp_slope=np.array([2.0]),
        sbp_curve_exposure_mmhg=sbp_x,
        sbp_curve_log_rr=nonlinear[None, None, :],
        sbp_age_attenuation=np.array([[1.0]]),
        mediated_outcomes=("nonlinear",),
        sodium_curve_exposure_g=inputs.sodium_curve_exposure_g,
        stomach_curve_log_rr=inputs.stomach_curve_log_rr[:1],
    )
    result = evaluate_sodium_mean_shift(
        one, baseline_scale=1.0, meal_sodium_g=1.0, quadrature_order=40
    )

    grid = np.linspace(50.0, 220.0, 200_001)
    density = np.exp(-0.5 * ((grid - 132.0) / 13.0) ** 2)
    density /= _trapezoid(density, grid)
    base = _trapezoid(np.exp(np.interp(grid, sbp_x, nonlinear)) * density, grid)
    shifted = _trapezoid(
        np.exp(np.interp(grid + 2.0, sbp_x, nonlinear)) * density, grid
    )
    assert result.mediated_risk_ratio[0, 0, 0, 0] == pytest.approx(
        shifted / base, rel=2e-5
    )


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"baseline_scale": -0.1, "meal_sodium_g": 1.0}, "baseline_scale"),
        ({"baseline_scale": 1.1, "meal_sodium_g": 1.0}, "baseline_scale"),
        ({"baseline_scale": 0.5, "meal_sodium_g": -1.0}, "meal_sodium_g"),
    ],
)
def test_invalid_interventions_are_rejected(kwargs, match):
    with pytest.raises(ValueError, match=match):
        evaluate_sodium_mean_shift(_linear_inputs(), **kwargs)
