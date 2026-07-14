# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the GBD/WPP nutrient-baseline builder and bundled output."""

from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

from mealhealth import data

SCRIPT = Path(__file__).parents[1] / "tools" / "build_baseline_nutrients_from_gbd.py"
SPEC = importlib.util.spec_from_file_location(
    "build_baseline_nutrients_from_gbd", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wpp_rows(countries=("USA", "FRA")):
    rows = []
    starts = list(range(25, 95, 5)) + [95, 100]
    for country in countries:
        for start in starts:
            rows.append(
                {
                    "ISO3_code": country,
                    "Variant": "Medium",
                    "Time": 2020,
                    "AgeGrpStart": start,
                    "AgeGrpSpan": 5 if start < 100 else -1,
                    "PopMale": 1.0,
                    "PopFemale": 3.0 if country == "USA" else 1.0,
                }
            )
    return rows


def test_wpp_weights_fold_95_plus(tmp_path):
    path = tmp_path / "wpp.csv"
    rows = _wpp_rows(("USA",))
    for row in rows:
        if row["AgeGrpStart"] == 95:
            row["PopMale"], row["PopFemale"] = 10.0, 30.0
        elif row["AgeGrpStart"] == 100:
            row["PopMale"], row["PopFemale"] = 20.0, 40.0
    pd.DataFrame(rows).to_csv(path, index=False)
    weights = builder._wpp_age_sex_weights(path, {"USA"})
    age_95 = weights.query("age_group_id == 235").set_index("sex_id")
    assert age_95.loc[1, "population"] == pytest.approx(30.0)
    assert age_95.loc[2, "population"] == pytest.approx(70.0)


def _write_synthetic_inputs(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    source_dir = raw / "diet"
    source_dir.mkdir(parents=True)
    exposure_path = source_dir / "omega3.csv"

    age_names = {
        age_id: ("95 plus" if start == 95 else f"{start} to {start + 4}")
        for age_id, start in builder.ADULT_AGE_START.items()
    }
    rows = []
    for year in range(1990, 2024):
        for location_id, location_name, country in (
            (102, "United States of America", "USA"),
            (80, "France", "FRA"),
        ):
            for age_id, age_name in age_names.items():
                for sex_id, sex in ((1, "Male"), (2, "Female")):
                    if country == "USA":
                        mean = 0.1 if sex_id == 1 else 0.3
                    else:
                        mean = 0.4 if sex_id == 1 else 0.6
                    rows.append(
                        {
                            "age_group_id": age_id,
                            "age_group_name": age_name,
                            "sex_id": sex_id,
                            "sex": sex,
                            "year_id": year,
                            "location_id": location_id,
                            "location_name": location_name,
                            "measure_id": 19,
                            "measure": "continuous",
                            "mean": mean,
                            "lower": mean - 0.01,
                            "upper": mean + 0.01,
                        }
                    )
    pd.DataFrame(rows, columns=builder.EXPOSURE_COLUMNS).to_csv(
        exposure_path, index=False
    )

    mortality_path = tmp_path / "mortality.csv"
    pd.DataFrame(
        {
            "location_id": [102, 80],
            "location_name": ["United States of America", "France"],
        }
    ).to_csv(mortality_path, index=False)
    wpp_path = tmp_path / "wpp.csv"
    pd.DataFrame(_wpp_rows()).to_csv(wpp_path, index=False)
    baseline_path = tmp_path / "baseline.csv"
    pd.DataFrame({"country": ["GUF", "FRA", "USA"]}).to_csv(baseline_path, index=False)

    monkeypatch.setattr(builder, "RAW_DIR", raw)
    source = builder.NutrientSource(
        "omega3", "diet/omega3.csv", _hash(exposure_path), "g/day"
    )
    return source, baseline_path, mortality_path, wpp_path, exposure_path


def test_builder_population_weights_proxy_and_determinism(tmp_path, monkeypatch):
    source, baseline, mortality, wpp, _ = _write_synthetic_inputs(tmp_path, monkeypatch)
    result = builder.build_baseline_nutrients(
        source=source,
        baseline_intake_path=baseline,
        mortality_path=mortality,
        wpp_path=wpp,
    )
    values = result.set_index("country")
    # USA uses 1:3 male:female weights; France uses equal weights.
    assert values.loc["USA", "intake_g_per_day"] == pytest.approx(0.25)
    assert values.loc["FRA", "intake_g_per_day"] == pytest.approx(0.5)
    assert values.loc["GUF", "intake_g_per_day"] == pytest.approx(0.5)
    assert values.loc["GUF", "source_country"] == "FRA"
    assert list(result["country"]) == ["FRA", "GUF", "USA"]

    first, second = tmp_path / "first.csv", tmp_path / "second.csv"
    builder.write_baseline_nutrients(result, first)
    builder.write_baseline_nutrients(result, second)
    assert first.read_bytes() == second.read_bytes()


def test_builder_rejects_checksum_and_schema(tmp_path, monkeypatch):
    source, _, _, _, exposure_path = _write_synthetic_inputs(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        builder._read_and_validate_exposure(replace(source, sha256="0" * 64))

    malformed = pd.read_csv(exposure_path).rename(columns={"mean": "value"})
    malformed.to_csv(exposure_path, index=False)
    bad_schema = replace(source, sha256=_hash(exposure_path))
    with pytest.raises(ValueError, match="Unexpected schema"):
        builder._read_and_validate_exposure(bad_schema)


def test_bundled_nutrient_coverage_and_provenance():
    nutrients = data.baseline_nutrients()
    countries = set(data.available_countries())
    assert set(nutrients["country"]) == countries
    assert set(nutrients["nutrient"]) == {"omega3"}
    assert set(nutrients["source_year"]) == {2020}
    proxies = nutrients[nutrients["source_country"] != nutrients["country"]]
    assert list(
        proxies[["country", "source_country"]].itertuples(index=False, name=None)
    ) == [("GUF", "FRA")]
