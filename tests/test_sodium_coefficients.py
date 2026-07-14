# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Reproducibility tests for the sodium-to-SBP reference artifact."""

import importlib.util
from pathlib import Path
import sys

import pytest

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
