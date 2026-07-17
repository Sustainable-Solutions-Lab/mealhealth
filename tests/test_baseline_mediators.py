# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the GBD sodium/SBP mediator-baseline builder."""

from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

from mealhealth import data

SCRIPT = Path(__file__).parents[1] / "tools" / "build_baseline_mediators_from_gbd.py"
SPEC = importlib.util.spec_from_file_location(
    "build_baseline_mediators_from_gbd", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_exposure(path: Path, *, scale: float) -> None:
    rows = []
    for year in range(1990, 2024):
        for location_id, location_name, offset in (
            (102, "United States of America", 1.0),
            (80, "France", 2.0),
        ):
            for age_id, age_name in builder.ADULT_AGE_NAME.items():
                for sex_id, sex in ((1, "Male"), (2, "Female")):
                    mean = scale * (offset + age_id / 100 + sex_id / 1000)
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
                            "lower": mean * 0.9,
                            "upper": mean * 1.1,
                        }
                    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=builder.EXPOSURE_COLUMNS).to_csv(path, index=False)


def _synthetic_inputs(tmp_path):
    raw = tmp_path / "raw"
    sodium_path = raw / "diet" / "sodium.csv"
    sbp_path = raw / "other" / "sbp.csv"
    _write_exposure(sodium_path, scale=2.0)
    _write_exposure(sbp_path, scale=100.0)
    sodium_source = builder.ExposureSource(
        "sodium_urinary", "diet/sodium.csv", _hash(sodium_path), "g/day"
    )
    sbp_source = builder.ExposureSource(
        "sbp", "other/sbp.csv", _hash(sbp_path), "mm Hg"
    )
    hierarchy_path = raw / "hierarchy.xlsx"
    pd.DataFrame(
        {
            "Location ID": [102, 80],
            "Location Name": ["United States of America", "France"],
            "Level": [3, 3],
        }
    ).to_excel(hierarchy_path, sheet_name="GBD 2021 Locations Hierarchy", index=False)
    baseline_path = tmp_path / "baseline.csv"
    pd.DataFrame({"country": ["USA", "FRA", "GUF"]}).to_csv(baseline_path, index=False)
    return raw, baseline_path, hierarchy_path, sodium_source, sbp_source


def test_builder_preserves_strata_bounds_proxy_and_determinism(tmp_path):
    raw, baseline, hierarchy, sodium_source, sbp_source = _synthetic_inputs(tmp_path)
    result = builder.build_baseline_mediators(
        raw_dir=raw,
        manifest_path=baseline,
        location_hierarchy_path=hierarchy,
        sodium_source=sodium_source,
        sbp_source=sbp_source,
    )
    assert len(result) == 3 * 15 * 2
    usa = result.query("country == 'USA' and age == '25-29' and sex == 'male'").iloc[0]
    assert usa["sodium_urinary_g_per_day_mean"] == pytest.approx(2.202)
    assert usa["sbp_mmhg_mean"] == pytest.approx(110.1)
    assert usa["sodium_urinary_g_per_day_lower"] == pytest.approx(2.202 * 0.9)
    assert usa["sbp_mmhg_upper"] == pytest.approx(110.1 * 1.1)

    french = result.query("country in ['FRA', 'GUF']").sort_values(
        ["age", "sex", "country"]
    )
    direct = (
        french.query("country == 'FRA'")
        .drop(columns=["country", "source_country"])
        .reset_index(drop=True)
    )
    proxy = (
        french.query("country == 'GUF'")
        .drop(columns=["country", "source_country"])
        .reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(direct, proxy)
    assert set(result.query("country == 'GUF'")["source_country"]) == {"FRA"}

    first, second = tmp_path / "first.csv", tmp_path / "second.csv"
    builder.write_baseline_mediators(result, first)
    builder.write_baseline_mediators(result, second)
    assert first.read_bytes() == second.read_bytes()


def test_builder_rejects_checksum_and_incomplete_join(tmp_path):
    raw, baseline, hierarchy, sodium_source, sbp_source = _synthetic_inputs(tmp_path)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        builder._read_and_validate_exposure(
            replace(sbp_source, sha256="0" * 64), raw_dir=raw
        )

    sbp = pd.read_csv(sbp_source.path(raw))
    sbp = sbp[
        ~(
            (sbp["location_id"] == 102)
            & (sbp["age_group_id"] == 10)
            & (sbp["sex_id"] == 1)
        )
    ]
    sbp.to_csv(sbp_source.path(raw), index=False)
    changed = replace(sbp_source, sha256=_hash(sbp_source.path(raw)))
    with pytest.raises(ValueError, match="Expected .* source mediator rows"):
        builder.build_baseline_mediators(
            raw_dir=raw,
            manifest_path=baseline,
            location_hierarchy_path=hierarchy,
            sodium_source=sodium_source,
            sbp_source=changed,
        )


def test_bundled_mediator_coverage_and_provenance():
    mediators = data.baseline_mediators()
    assert len(mediators) == len(data.available_countries()) * 15 * 2
    assert set(mediators["source_year"]) == {2020}
    proxies = mediators[mediators["source_country"] != mediators["country"]]
    assert set(
        proxies[["country", "source_country"]].itertuples(index=False, name=None)
    ) == {("GUF", "FRA")}
