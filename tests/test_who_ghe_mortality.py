# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""WHO GHE mortality retrieval, preparation, and bundled-data checks."""

import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

from mealhealth import data
from mealhealth.foodgroups import AGE_BUCKETS, CAUSES

SCRIPT = Path(__file__).parents[1] / "tools" / "prepare_data.py"
SPEC = importlib.util.spec_from_file_location("prepare_data_who_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
prepare = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prepare
SPEC.loader.exec_module(prepare)


def _write_who_export(path: Path) -> None:
    rows = []
    age_codes = [*prepare.WHO_GHE_AGE_MAP, prepare.WHO_GHE_OPEN_AGE]
    for country in sorted(set(prepare.MORTALITY_COUNTRY_PROXIES.values())):
        for sex, sex_factor in (("MALE", 2.0), ("FEMALE", 1.0)):
            for cause_id in prepare.WHO_GHE_CAUSE_MAP:
                for age_code in age_codes:
                    rate = sex_factor * (10.0 if age_code == "YGE_85" else 2.0)
                    rows.append(
                        {
                            "DIM_COUNTRY_CODE": country,
                            "DIM_YEAR_CODE": prepare.REFERENCE_YEAR,
                            "DIM_AGEGROUP_CODE": age_code,
                            "DIM_SEX_CODE": sex,
                            "DIM_GHECAUSE_CODE": cause_id,
                            "DIM_GHECAUSE_TITLE": prepare.WHO_GHE_CAUSE_TITLES[
                                cause_id
                            ],
                            "ATTR_POPULATION_NUMERIC": 1000.0,
                            "VAL_DTHS_RATE100K_NUMERIC": rate,
                            "VAL_DTHS_COUNT_NUMERIC": rate / 100.0,
                        }
                    )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_who_preparation_aggregates_causes_expands_open_age_and_proxies(tmp_path):
    raw = tmp_path / "who.csv"
    _write_who_export(raw)
    result = prepare.build_mortality(raw)

    usa = result.query("country == 'USA'")
    assert len(usa) == 2 * len(CAUSES) * len(AGE_BUCKETS)
    assert set(usa["sex"]) == {"male", "female"}
    # WHO's two chronic-kidney components are added.
    ckd = usa.query("sex == 'female' and cause == 'CKD' and age == '60-64'")
    assert ckd["death_rate_per_1000"].item() == pytest.approx(0.04)
    # WHO publishes one 85+ rate; it is repeated over mealhealth's finer bands.
    oldest = usa.query("sex == 'female' and cause == 'CHD'").set_index("age")
    assert oldest.loc["85-89", "death_rate_per_1000"] == pytest.approx(0.1)
    assert oldest.loc["90-94", "death_rate_per_1000"] == pytest.approx(0.1)
    assert oldest.loc["95+", "death_rate_per_1000"] == pytest.approx(0.1)
    assert oldest.loc["60-64", "death_rate_per_1000"] == pytest.approx(0.02)
    male = usa.query("sex == 'male' and cause == 'CHD' and age == '60-64'")
    assert male["death_rate_per_1000"].item() == pytest.approx(0.04)
    assert set(result.query("country == 'ASM'")["country"]) == {"ASM"}
    assert set(result.query("country == 'ASM'")["source_country"]) == {"WSM"}


def test_retrieval_queries_each_cause_and_sex_without_truncation(monkeypatch):
    calls = []

    def fake_get(params):
        calls.append(params)
        return prepare.WhoGhePage(
            value=[
                {
                    "DIM_COUNTRY_CODE": "USA",
                    "DIM_YEAR_CODE": 2020,
                    "DIM_AGEGROUP_CODE": "Y60T64",
                    "DIM_SEX_CODE": "MALE",
                    "DIM_GHECAUSE_CODE": 640,
                    "DIM_GHECAUSE_TITLE": "Stomach cancer",
                    "ATTR_POPULATION_NUMERIC": 1000.0,
                    "VAL_DTHS_RATE100K_NUMERIC": 2.0,
                    "VAL_DTHS_COUNT_NUMERIC": 0.02,
                }
            ]
        )

    monkeypatch.setattr(prepare, "_who_ghe_get", fake_get)
    result = prepare.retrieve_who_ghe_mortality()
    assert len(result) == 2 * len(prepare.WHO_GHE_CAUSE_MAP)
    assert len(calls) == len(result)
    assert all("DIM_SEX_CODE eq" in call["$filter"] for call in calls)
    assert all(call["$top"] == 10000 for call in calls)


def test_bundled_who_mortality_is_complete_and_sex_specific():
    mortality = data.mortality()
    assert set(mortality.columns) == {
        "country",
        "sex",
        "cause",
        "age",
        "source_country",
        "death_rate_per_1000",
    }
    assert set(mortality["sex"]) == {"male", "female"}
    assert set(mortality["cause"]) == set(CAUSES)
    assert set(mortality["age"]) == set(AGE_BUCKETS)
    usa = mortality.query("country == 'USA' and age == '60-64'")
    by_sex = usa.groupby("sex")["death_rate_per_1000"].sum()
    assert by_sex["male"] != pytest.approx(by_sex["female"])
