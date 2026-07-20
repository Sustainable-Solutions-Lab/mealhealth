#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
# SPDX-License-Identifier: GPL-3.0-or-later

"""Regenerate all processed data bundled with :mod:`mealhealth`.

The public raw files which cannot be downloaded automatically must be placed
under ``data/raw/`` first; see ``docs/development/data_build.md``.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
import tempfile

from tools import (
    build_baseline_calories,
    build_baseline_exposure,
    build_baseline_mediators_from_gbd,
    build_sodium_relative_risks,
    dietary_exposure_sources,
    prepare_data,
)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PACKAGED_DATA = ROOT / "src" / "mealhealth" / "data"


@dataclass(frozen=True)
class Stage:
    """One ordered builder function and the files it must produce."""

    name: str
    runner: Callable[[Path], object]
    outputs: tuple[str, ...]


def _build_and_write_baseline_exposure(output_dir: Path) -> object:
    return build_baseline_exposure.build_and_write_baseline_exposure(
        output=output_dir / "baseline_exposure.csv"
    )


def _build_and_write_baseline_calories(output_dir: Path) -> object:
    return build_baseline_calories.build_and_write_baseline_calories(
        output=output_dir / "baseline_calories.csv"
    )


def _build_and_write_health_data(output_dir: Path) -> object:
    return prepare_data.build_and_write_health_data(output_dir=output_dir)


def _build_and_write_baseline_mediators(output_dir: Path) -> object:
    return build_baseline_mediators_from_gbd.build_and_write_baseline_mediators(
        output=output_dir / "baseline_mediators.csv"
    )


def _build_and_write_sodium_relative_risks(output_dir: Path) -> object:
    return build_sodium_relative_risks.build_and_write_relative_risks(
        output=output_dir / "sodium_relative_risks.csv"
    )


STAGES = (
    Stage(
        "direct exposure baseline",
        _build_and_write_baseline_exposure,
        ("baseline_exposure.csv",),
    ),
    Stage(
        "calorie baseline",
        _build_and_write_baseline_calories,
        ("baseline_calories.csv",),
    ),
    Stage(
        "health and demographic data",
        _build_and_write_health_data,
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
        _build_and_write_baseline_mediators,
        ("baseline_mediators.csv",),
    ),
    Stage(
        "sodium and SBP relative risks",
        _build_and_write_sodium_relative_risks,
        ("sodium_relative_risks.csv",),
    ),
)


def manual_inputs() -> tuple[Path, ...]:
    """Return raw inputs that the workflow cannot obtain automatically."""

    direct_inputs = tuple(
        source.path(RAW) for source in dietary_exposure_sources.DIRECT_SOURCES.values()
    )
    mediator_inputs = tuple(
        source.path(RAW)
        for source in dietary_exposure_sources.MEDIATOR_SOURCES.values()
    )
    return (
        *direct_inputs,
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
        "Run 'python -m tools.build_data --list-inputs' for the full list, or "
        "see docs/development/data_build.md for download instructions.",
    ]
    raise FileNotFoundError("\n".join(lines))


def pinned_digests() -> dict[Path, str]:
    """Return the pinned SHA-256 for every manual input that has one."""

    return {
        source.path(RAW): source.sha256
        for source in (
            *dietary_exposure_sources.DIRECT_SOURCES.values(),
            *dietary_exposure_sources.MEDIATOR_SOURCES.values(),
        )
    }


def list_manual_inputs() -> None:
    """Print every manually staged input, its status, and its pinned digest.

    This is the authoritative list; the documentation points here rather than
    repeating it, so the two cannot drift apart.
    """

    digests = pinned_digests()
    inputs = manual_inputs()
    print(f"{len(inputs)} manually staged inputs, relative to {ROOT}:\n")
    for path in inputs:
        status = "present" if path.exists() else "MISSING"
        print(f"[{status:>7}] {path.relative_to(ROOT)}")
        digest = digests.get(path)
        if digest:
            print(f"            sha256 {digest}")
    missing = sum(1 for path in inputs if not path.exists())
    print(
        f"\n{len(inputs) - missing} present, {missing} missing. "
        "See docs/development/data_build.md for where to download each one."
    )


def run_stage(stage: Stage, output_dir: Path) -> None:
    """Run one builder function and verify its declared outputs."""

    print(f"\n==> {stage.name}")
    stage.runner(output_dir)
    missing = [
        output_dir / output
        for output in stage.outputs
        if not (output_dir / output).is_file()
    ]
    if missing:
        names = ", ".join(str(path) for path in missing)
        raise RuntimeError(f"{stage.name} completed without writing: {names}")


def publish_outputs(stages: tuple[Stage, ...], staging_dir: Path) -> None:
    """Publish verified staged outputs to the package data directory."""

    output_names = [name for stage in stages for name in stage.outputs]
    if len(output_names) != len(set(output_names)):
        raise RuntimeError("Data-build stages declare duplicate output files")
    missing = [name for name in output_names if not (staging_dir / name).is_file()]
    if missing:
        raise RuntimeError(
            f"Cannot publish missing staged outputs: {', '.join(missing)}"
        )
    PACKAGED_DATA.mkdir(parents=True, exist_ok=True)
    for name in output_names:
        (staging_dir / name).replace(PACKAGED_DATA / name)


def main(argv: Sequence[str] | None = None) -> None:
    """Validate manual inputs, download public inputs, and run every stage."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list-inputs",
        action="store_true",
        help="list the manually staged raw inputs and exit without building",
    )
    args = parser.parse_args(argv)
    if args.list_inputs:
        list_manual_inputs()
        return

    check_manual_inputs()
    print("Ensuring automatically downloadable public inputs are available ...")
    prepare_data.ensure_raw_downloads()
    build_baseline_calories.ensure_source()
    PACKAGED_DATA.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".mealhealth-data-build-", dir=PACKAGED_DATA.parent
    ) as temporary_dir:
        staging_dir = Path(temporary_dir)
        for stage in STAGES:
            run_stage(stage, staging_dir)
        publish_outputs(STAGES, staging_dir)
    print("\nData build completed successfully.")


if __name__ == "__main__":
    main()
