#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validate sodium-to-SBP reference conversions and optional source hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REFERENCE = ROOT / "tools" / "reference" / "sodium_to_sbp.json"


def validate_reference(reference_path: Path, source_dir: Path | None = None) -> None:
    with reference_path.open(encoding="utf-8") as handle:
        reference = json.load(handle)
    _validate_structure(reference)
    conversion = float(reference["grams_sodium_per_100_mmol"])

    for model in reference["linear_models"]:
        factor = 1.0 if "per g/day" in model["native_unit"] else conversion
        for suffix in ("estimate", "ci_lower", "ci_upper"):
            expected = float(model[f"native_{suffix}"]) / factor
            actual = float(model[f"canonical_{suffix}"])
            if not np.isclose(actual, expected, rtol=0.0, atol=5e-12):
                raise ValueError(
                    f"{model['id']} canonical_{suffix}={actual} does not match "
                    f"native conversion {expected}"
                )

    coefficients = reference["mozaffarian_transport_model"]["coefficients"]
    for name, coefficient in coefficients.items():
        for suffix in ("estimate", "se"):
            expected = float(coefficient[f"native_{suffix}"]) / conversion
            actual = float(coefficient[f"canonical_{suffix}"])
            if not np.isclose(actual, expected, rtol=0.0, atol=5e-12):
                raise ValueError(
                    f"Mozaffarian {name} canonical_{suffix}={actual} does not "
                    f"match native conversion {expected}"
                )

    if source_dir is not None:
        for source, metadata in reference["source_files"].items():
            path = source_dir / metadata["filename"]
            if not path.is_file():
                raise FileNotFoundError(f"Missing source file for {source}: {path}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != metadata["sha256"]:
                raise ValueError(
                    f"SHA-256 mismatch for {source}: expected "
                    f"{metadata['sha256']}, got {digest}"
                )


def _validate_structure(reference: dict[str, Any]) -> None:
    if reference.get("schema_version") != 1:
        raise ValueError("Unsupported sodium coefficient schema")
    if reference.get("canonical_unit") != "mm Hg per g/day urinary sodium":
        raise ValueError("Unexpected canonical sodium-to-SBP unit")
    conversion = reference.get("grams_sodium_per_100_mmol")
    if not isinstance(conversion, (int, float)) or not np.isclose(conversion, 2.299):
        raise ValueError("Unexpected sodium mass conversion")
    recovery = reference.get("dietary_to_urinary", {})
    if not (
        recovery.get("ci_lower")
        <= recovery.get("central_fraction")
        <= recovery.get("ci_upper")
    ) or not np.isclose(recovery.get("central_fraction"), 0.928):
        raise ValueError("Unexpected dietary-to-urinary sodium conversion")
    tmrel = reference.get("sodium_tmrel", {})
    if (
        tmrel.get("distribution") != "uniform"
        or not np.isclose(tmrel.get("lower_g_per_day_urinary"), 1.0)
        or not np.isclose(tmrel.get("upper_g_per_day_urinary"), 5.0)
    ):
        raise ValueError("Unexpected sodium TMREL specification")
    models = reference.get("linear_models")
    if not isinstance(models, list) or not models:
        raise ValueError("linear_models must be a non-empty list")
    identifiers = [model.get("id") for model in models]
    if len(identifiers) != len(set(identifiers)) or None in identifiers:
        raise ValueError("linear model IDs must be present and unique")
    primary = [model for model in models if model.get("role") == "primary"]
    if len(primary) != 1 or primary[0]["id"] != "filippini_primary":
        raise ValueError("Exactly one Filippini primary model is required")
    for model in models:
        if not (
            model["canonical_ci_lower"]
            <= model["canonical_estimate"]
            <= model["canonical_ci_upper"]
        ):
            raise ValueError(f"Invalid confidence interval for {model['id']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Optional directory containing the exact source filenames to hash-check",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    validate_reference(arguments.reference, arguments.source_dir)
    print(f"Validated {arguments.reference}")
