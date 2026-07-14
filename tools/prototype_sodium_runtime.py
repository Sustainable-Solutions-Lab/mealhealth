#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Benchmark the compact, draw-preserving sodium runtime design.

This is a synthetic performance gate, not a source-data builder and not a
scientific sodium result.  It models the intended bundle shapes, loads one
country from a compressed archive, evaluates all first-release outcome paths,
and reports preliminary Monte Carlo stability.

Run from the repository root::

    python tools/prototype_sodium_runtime.py --draws 500
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import tracemalloc

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mealhealth.sodium import (  # noqa: E402, I001
    SodiumRuntimeInputs,
    evaluate_prepared_sodium,
    prepare_sodium_runtime,
)


MEDIATED_OUTCOMES = (
    "ischemic_heart_disease",
    "ischemic_stroke",
    "intracerebral_hemorrhage",
    "subarachnoid_hemorrhage",
    "peripheral_arterial_disease",
    "aortic_aneurysm",
    "ckd_type_2_diabetes",
    "ckd_hypertension",
    "ckd_glomerulonephritis",
    "ckd_other",
)


def synthetic_inputs(draws: int, rng: np.random.Generator) -> SodiumRuntimeInputs:
    """Construct plausible-shaped, explicitly non-scientific draw inputs."""

    ages, sexes = 15, 2
    age = np.arange(ages, dtype=np.float32)[None, :, None]
    sex = np.arange(sexes, dtype=np.float32)[None, None, :]
    draw_common = rng.normal(0.0, 1.0, (draws, 1, 1)).astype(np.float32)

    u0 = (
        3.2
        + 0.03 * age
        + 0.20 * sex
        + 0.18 * draw_common
        + rng.normal(0.0, 0.05, (draws, ages, sexes))
    ).astype(np.float32)
    sbp_mean = (
        121.0
        + 1.65 * age
        + 2.5 * sex
        + 1.7 * draw_common
        + rng.normal(0.0, 0.35, (draws, ages, sexes))
    ).astype(np.float32)
    sbp_sd = (
        12.5
        + 0.20 * age
        + 0.35 * sex
        + 0.35 * draw_common
        + rng.normal(0.0, 0.15, (draws, ages, sexes))
    ).astype(np.float32)
    sbp_sd = np.maximum(sbp_sd, np.float32(8.0))

    recovery = np.clip(rng.normal(0.928, 0.011, draws), 0.85, 1.0).astype(np.float32)
    tmrel = rng.uniform(1.0, 5.0, draws).astype(np.float32)
    slope = np.maximum(rng.normal(2.42, 0.23, draws), 0.05).astype(np.float32)

    sbp_x = np.linspace(115.0, 200.0, 43, dtype=np.float32)
    base_log_rr_per_10 = np.linspace(
        np.log(1.18), np.log(1.55), len(MEDIATED_OUTCOMES), dtype=np.float32
    )
    curve_draw_scale = np.exp(
        rng.normal(0.0, 0.08, (draws, len(MEDIATED_OUTCOMES), 1))
    ).astype(np.float32)
    curve_power = np.linspace(0.92, 1.18, len(MEDIATED_OUTCOMES), dtype=np.float32)[
        None, :, None
    ]
    sbp_distance = ((sbp_x - sbp_x[0]) / 10.0)[None, None, :]
    sbp_log_rr = (
        curve_draw_scale
        * base_log_rr_per_10[None, :, None]
        * np.power(sbp_distance, curve_power)
    ).astype(np.float32)
    age_attenuation = np.broadcast_to(
        np.linspace(1.45, 0.55, ages, dtype=np.float32),
        (len(MEDIATED_OUTCOMES), ages),
    ).copy()

    sodium_x = np.linspace(1.14, 7.36, 32, dtype=np.float32)
    stomach_scale = np.exp(rng.normal(0.0, 0.10, (draws, 1))).astype(np.float32)
    stomach_distance = (sodium_x - sodium_x[0]) / (sodium_x[-1] - sodium_x[0])
    stomach_log_rr = (
        stomach_scale * np.log(1.35) * np.power(stomach_distance[None, :], 1.10)
    ).astype(np.float32)

    return SodiumRuntimeInputs(
        baseline_urinary_g=u0,
        sbp_mean_mmhg=sbp_mean,
        sbp_sd_mmhg=sbp_sd,
        recovery_fraction=recovery,
        sodium_tmrel_g=tmrel,
        sodium_to_sbp_slope=slope,
        sbp_curve_exposure_mmhg=sbp_x,
        sbp_curve_log_rr=sbp_log_rr,
        sbp_age_attenuation=age_attenuation,
        mediated_outcomes=MEDIATED_OUTCOMES,
        sodium_curve_exposure_g=sodium_x,
        stomach_curve_log_rr=stomach_log_rr,
    )


def bundle_payload(
    inputs: SodiumRuntimeInputs,
    countries: int,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Construct a lazy-loadable NPZ payload with one member per country."""

    draws, ages, sexes = inputs.baseline_urinary_g.shape
    country_data = np.empty((countries, draws, ages, sexes, 3), dtype=np.float32)
    base = np.stack(
        (inputs.baseline_urinary_g, inputs.sbp_mean_mmhg, inputs.sbp_sd_mmhg),
        axis=-1,
    )
    country_data[:] = base
    # Independent country offsets/noise avoid an unrealistically compressible
    # size estimate while preserving plausible scales and valid positive SDs.
    country_data[..., 0] += rng.normal(
        0.0, 0.30, (countries, draws, ages, sexes)
    ).astype(np.float32)
    country_data[..., 1] += rng.normal(
        0.0, 4.0, (countries, draws, ages, sexes)
    ).astype(np.float32)
    country_data[..., 2] += rng.normal(
        0.0, 0.8, (countries, draws, ages, sexes)
    ).astype(np.float32)
    country_data[..., 0] = np.maximum(country_data[..., 0], 0.1)
    country_data[..., 2] = np.maximum(country_data[..., 2], 5.0)

    payload = {
        "recovery_fraction": inputs.recovery_fraction,
        "sodium_tmrel_g": inputs.sodium_tmrel_g,
        "sodium_to_sbp_slope": inputs.sodium_to_sbp_slope,
        "sbp_curve_exposure_mmhg": inputs.sbp_curve_exposure_mmhg,
        "sbp_curve_log_rr": inputs.sbp_curve_log_rr,
        "sbp_age_attenuation": inputs.sbp_age_attenuation,
        "sodium_curve_exposure_g": inputs.sodium_curve_exposure_g,
        "stomach_curve_log_rr": inputs.stomach_curve_log_rr,
    }
    payload.update(
        {f"country_{index:03d}": country_data[index] for index in range(countries)}
    )
    return payload


def inputs_from_archive(archive: np.lib.npyio.NpzFile) -> SodiumRuntimeInputs:
    country = archive["country_000"]
    return SodiumRuntimeInputs(
        baseline_urinary_g=country[..., 0],
        sbp_mean_mmhg=country[..., 1],
        sbp_sd_mmhg=country[..., 2],
        recovery_fraction=archive["recovery_fraction"],
        sodium_tmrel_g=archive["sodium_tmrel_g"],
        sodium_to_sbp_slope=archive["sodium_to_sbp_slope"],
        sbp_curve_exposure_mmhg=archive["sbp_curve_exposure_mmhg"],
        sbp_curve_log_rr=archive["sbp_curve_log_rr"],
        sbp_age_attenuation=archive["sbp_age_attenuation"],
        mediated_outcomes=MEDIATED_OUTCOMES,
        sodium_curve_exposure_g=archive["sodium_curve_exposure_g"],
        stomach_curve_log_rr=archive["stomach_curve_log_rr"],
    )


def aggregate_synthetic_draws(result, rng: np.random.Generator) -> np.ndarray:
    """Create a stable scalar per draw solely for convergence diagnostics."""

    mediated_weights = rng.uniform(0.2, 2.0, result.mediated_risk_ratio.shape[1:])
    stomach_weights = rng.uniform(0.2, 2.0, result.stomach_risk_ratio.shape[1:])
    mediated_weights /= mediated_weights.sum()
    stomach_weights /= stomach_weights.sum()
    return np.sum(
        (1.0 - result.mediated_risk_ratio) * mediated_weights[None, ...],
        axis=(1, 2, 3),
    ) + np.sum(
        (1.0 - result.stomach_risk_ratio) * stomach_weights[None, ...],
        axis=(1, 2),
    )


def distribution_summary(values: np.ndarray) -> dict[str, float]:
    lower, upper = np.quantile(values, (0.025, 0.975))
    return {
        "mean": float(np.mean(values)),
        "lower": float(lower),
        "upper": float(upper),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    rng = np.random.default_rng(args.seed)
    inputs = synthetic_inputs(args.draws, rng)

    with tempfile.TemporaryDirectory(prefix="mealhealth-sodium-") as directory:
        artifact = Path(directory) / "synthetic_sodium_draws.npz"
        np.savez_compressed(artifact, **bundle_payload(inputs, args.countries, rng))
        bundle_mib = artifact.stat().st_size / 1024**2

        tracemalloc.start()
        cold_start = time.perf_counter()
        with np.load(artifact, allow_pickle=False) as archive:
            loaded = inputs_from_archive(archive)
            prepared = prepare_sodium_runtime(
                loaded,
                quadrature_order=args.quadrature_order,
            )
            cold_result = evaluate_prepared_sodium(
                prepared,
                baseline_scale=args.baseline_scale,
                meal_sodium_g=args.meal_sodium_g,
            )
        cold_ms = (time.perf_counter() - cold_start) * 1000
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        warm_times = []
        for _ in range(args.repeats):
            start = time.perf_counter()
            warm_result = evaluate_prepared_sodium(
                prepared,
                baseline_scale=args.baseline_scale,
                meal_sodium_g=args.meal_sodium_g,
            )
            warm_times.append((time.perf_counter() - start) * 1000)

    # Keep both variables live through the timing block and verify deterministic
    # replay before using the warm result for the convergence diagnostic.
    if not np.array_equal(
        cold_result.mediated_risk_ratio, warm_result.mediated_risk_ratio
    ):
        raise RuntimeError("cold and warm sodium evaluations differ")
    aggregate = aggregate_synthetic_draws(warm_result, rng)
    checkpoints = sorted({max(50, args.draws // 5), args.draws // 2, args.draws})
    convergence = {
        str(count): distribution_summary(aggregate[:count]) for count in checkpoints
    }

    return {
        "synthetic_only": True,
        "draws": args.draws,
        "countries": args.countries,
        "ages": inputs.baseline_urinary_g.shape[1],
        "sexes": inputs.baseline_urinary_g.shape[2],
        "mediated_outcomes": len(MEDIATED_OUTCOMES),
        "direct_outcomes": 1,
        "quadrature_order": args.quadrature_order,
        "bundle_mib": bundle_mib,
        "cold_ms": cold_ms,
        "warm_ms_median": float(np.median(warm_times)),
        "warm_ms_min": float(np.min(warm_times)),
        "tracemalloc_peak_mib": peak_bytes / 1024**2,
        "monte_carlo_prefixes": convergence,
        "seed": args.seed,
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "logical_cpus": os.cpu_count(),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draws", type=int, default=500)
    parser.add_argument("--countries", type=int, default=204)
    parser.add_argument("--quadrature-order", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--seed", type=int, default=20260714)
    parser.add_argument("--baseline-scale", type=float, default=0.80)
    parser.add_argument("--meal-sodium-g", type=float, default=1.50)
    args = parser.parse_args()
    if args.draws < 50 or args.countries < 1 or args.repeats < 1:
        parser.error("draws must be >=50; countries and repeats must be positive")
    return args


if __name__ == "__main__":
    print(json.dumps(run(parse_args()), indent=2, sort_keys=True))
