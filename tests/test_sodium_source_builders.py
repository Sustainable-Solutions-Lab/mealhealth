# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Source-reconstruction tests for the bundled sodium risk inputs."""

import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest


def _load_script(name: str):
    path = Path(__file__).parents[1] / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


curves_builder = _load_script("build_sodium_relative_risks")
age_builder = _load_script("generate_sbp_age_attenuation")


def test_curve_builder_validates_metadata_and_preserves_all_pairs(monkeypatch):
    def fake_get(endpoint, *, risk, cause):
        curve_cause = next(
            name
            for name, (_, rei_id, cause_id, _, _) in curves_builder.CURVES.items()
            if (rei_id, cause_id) == (risk, cause)
        )
        path, _, _, unit, stars = curves_builder.CURVES[curve_cause]
        if endpoint == "risk_cause_metadata":
            return {
                "risk_unit": unit,
                "star_rating": stars,
                "risk_lower": 1.0,
                "risk_upper": 5.0,
            }
        assert endpoint == "output_data"
        upper = 200.0 if path == "sbp" else 6.0
        return [
            {
                "risk": 1.0,
                "linear_cause_lower": 1.0,
                "linear_cause": 1.0,
                "linear_cause_upper": 1.0,
            },
            {
                "risk": upper,
                "linear_cause_lower": 1.1,
                "linear_cause": 1.2,
                "linear_cause_upper": 1.3,
            },
        ]

    monkeypatch.setattr(curves_builder, "_get", fake_get)
    result = curves_builder.build_relative_risks()
    assert len(result) == 2 * len(curves_builder.CURVES)
    assert set(result["curve_cause"]) == set(curves_builder.CURVES)
    assert set(result["path"]) == {"sbp", "sodium"}


def test_sbp_age_builder_normalizes_log_rr_at_60_64(tmp_path):
    rows = []
    marker = [None] * 28
    marker[0] = "High systolic blood pressure"
    rows.append(marker)
    for source_outcome in age_builder.OUTCOME_ROWS.values():
        row = [None] * 28
        row[0] = source_outcome
        row[1] = "10 mmHg"
        for column in age_builder.ADULT_AGE_COLUMNS:
            row[column] = "2.00 (1.50-2.50)"
        rows.append(row)
    end = [None] * 28
    end[0] = "Next risk"
    rows.append(end)
    source = tmp_path / "rr.xlsx"
    pd.DataFrame(rows).to_excel(source, header=False, index=False)

    result = age_builder.build_age_attenuation(source)
    assert len(result) == len(age_builder.OUTCOME_ROWS) * len(
        age_builder.ADULT_AGE_COLUMNS
    )
    assert result["beta"].to_list() == pytest.approx([1.0] * len(result))
