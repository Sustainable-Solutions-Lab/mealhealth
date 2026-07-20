#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
# SPDX-License-Identifier: GPL-3.0-or-later

"""Regenerate all processed data bundled with :mod:`mealhealth`.

The public raw files which cannot be downloaded automatically must be placed
under ``data/raw/`` first; see ``docs/data_sources.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PACKAGED_DATA = ROOT / "src" / "mealhealth" / "data"

# Make the development-only tools importable when this file is run directly.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import (  # noqa: E402
    build_baseline_calories,
    build_baseline_exposure,
    build_baseline_mediators_from_gbd,
    build_sodium_relative_risks,
    dietary_exposure_sources,
    prepare_data,
)


@dataclass(frozen=True)
class Stage:
    """One ordered builder function and the files it must produce."""

    name: str
    runner: Callable[[], object]
    outputs: tuple[str, ...]


STAGES = (
    Stage(
        "direct exposure baseline",
        build_baseline_exposure.build_and_write_baseline_exposure,
        ("baseline_exposure.csv",),
    ),
    Stage(
        "calorie baseline",
        build_baseline_calories.build_and_write_baseline_calories,
        ("baseline_calories.csv",),
    ),
    Stage(
        "health and demographic data",
        prepare_data.build_health_data,
        (
            "relative_risks.csv",
            "mortality.csv",
            "population.csv",
            "local_life_table.csv",
            "standard_life_table.csv",
        ),
    ),
    Stage(
        "sodium mediator baseline",
        build_baseline_mediators_from_gbd.build_and_write_baseline_mediators,
        ("baseline_mediators.csv",),
    ),
    Stage(
        "sodium and SBP relative risks",
        build_sodium_relative_risks.build_and_write_relative_risks,
        ("sodium_relative_risks.csv",),
    ),
)


def manual_inputs() -> tuple[Path, ...]:
    """Return raw inputs that the workflow cannot obtain automatically."""

    direct_inputs = tuple(
        RAW / source.relative_path
        for source in dietary_exposure_sources.DIRECT_SOURCES.values()
    )
    mediator_inputs = (
        build_baseline_mediators_from_gbd.SODIUM_SOURCE.path(RAW),
        build_baseline_mediators_from_gbd.SBP_SOURCE.path(RAW),
    )
    return (
        *direct_inputs,
        build_baseline_calories.DEFAULT_SOURCE,
        prepare_data.GBD_REFERENCE_LIFE_TABLE_CSV,
        *mediator_inputs,
    )


def check_manual_inputs() -> None:
    """Fail early with one actionable message for missing raw files."""

    missing = [path for path in manual_inputs() if not path.exists()]
    if not missing:
        return
    lines = [
        "Missing manually downloaded data required for the mealhealth data build:",
        *(f"  - {path.relative_to(ROOT)}" for path in missing),
        "See docs/data_sources.md for download instructions.",
    ]
    raise FileNotFoundError("\n".join(lines))


def run_stage(stage: Stage) -> None:
    """Run one builder function and verify its declared outputs."""

    print(f"\n==> {stage.name}")
    stage.runner()
    missing = [
        PACKAGED_DATA / output
        for output in stage.outputs
        if not (PACKAGED_DATA / output).exists()
    ]
    if missing:
        names = ", ".join(str(path.relative_to(ROOT)) for path in missing)
        raise RuntimeError(f"{stage.name} completed without writing: {names}")


def main() -> None:
    """Validate manual inputs, download public inputs, and run every stage."""

    check_manual_inputs()
    print("Ensuring automatically downloadable public inputs are available ...")
    prepare_data.ensure_raw_downloads()
    for stage in STAGES:
        run_stage(stage)
    print("\nData build completed successfully.")


if __name__ == "__main__":
    main()
