# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Reproducibility tests for the sodium-to-SBP reference artifact."""

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from mealhealth.sodium import (
    SODIUM_TMREL_HIGH_G_PER_DAY,
    SODIUM_TMREL_LOW_G_PER_DAY,
    SODIUM_TO_SBP_MMHG_PER_G,
    SODIUM_URINARY_RECOVERY,
)

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "tools" / "validate_sodium_coefficients.py"
REFERENCE = ROOT / "tools" / "reference" / "sodium_to_sbp.json"
SPEC = importlib.util.spec_from_file_location("validate_sodium_coefficients", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def test_sodium_coefficient_units_and_conversions():
    validator.validate_reference(REFERENCE)


def test_runtime_conversion_and_tmrel_match_reviewed_reference():
    reference = json.loads(REFERENCE.read_text())
    assert SODIUM_URINARY_RECOVERY == pytest.approx(
        reference["dietary_to_urinary"]["central_fraction"]
    )
    assert SODIUM_TMREL_LOW_G_PER_DAY == pytest.approx(
        reference["sodium_tmrel"]["lower_g_per_day_urinary"]
    )
    assert SODIUM_TMREL_HIGH_G_PER_DAY == pytest.approx(
        reference["sodium_tmrel"]["upper_g_per_day_urinary"]
    )
    primary = next(
        model for model in reference["linear_models"] if model["role"] == "primary"
    )
    assert SODIUM_TO_SBP_MMHG_PER_G == pytest.approx(primary["canonical_estimate"])


def test_sodium_coefficient_source_hashes_against_review_cache():
    """Run only when the reviewed primary-source cache is available locally."""

    expected = (
        "filippini_combined.pdf",
        "huang.pdf",
        "mozaffarian2014_supplement.pdf",
    )
    if not all((Path("/tmp") / name).is_file() for name in expected):
        pytest.skip("reviewed primary-source cache is not available")
    validator.validate_reference(REFERENCE, Path("/tmp"))
