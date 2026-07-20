# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Runtime schema checks at external JSON ingestion boundaries."""

from io import BytesIO
import json

import pytest

from tools import build_sodium_relative_risks, prepare_data


def _response(payload: object) -> BytesIO:
    return BytesIO(json.dumps(payload).encode())


def test_dietary_bop_ingestion_rejects_coerced_curve_values(monkeypatch) -> None:
    payload = [
        {
            "risk": "1.0",
            "linear_cause": 1.0,
            "linear_cause_lower": 1.0,
            "linear_cause_upper": 1.0,
        }
    ]
    monkeypatch.setattr(
        prepare_data.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _response(payload),
    )

    with pytest.raises(ValueError, match="output_data response failed schema"):
        prepare_data._bop_get("output_data", risk=111, cause=493)


def test_sodium_bop_ingestion_rejects_missing_metadata(monkeypatch) -> None:
    payload = {"risk_unit": "g/day", "risk_lower": 1.0, "risk_upper": 5.0}
    monkeypatch.setattr(
        build_sodium_relative_risks.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _response(payload),
    )

    with pytest.raises(ValueError, match="risk_cause_metadata response failed schema"):
        build_sodium_relative_risks._get("risk_cause_metadata", risk=124, cause=414)


def test_who_ingestion_rejects_wrong_scalar_types(monkeypatch) -> None:
    payload = {
        "value": [
            {
                "DIM_COUNTRY_CODE": "USA",
                "DIM_YEAR_CODE": "2020",
                "DIM_AGEGROUP_CODE": "Y60T64",
                "DIM_SEX_CODE": "MALE",
                "DIM_GHECAUSE_CODE": 640,
                "DIM_GHECAUSE_TITLE": "Stomach cancer",
                "ATTR_POPULATION_NUMERIC": 1000.0,
                "VAL_DTHS_RATE100K_NUMERIC": 2.0,
                "VAL_DTHS_COUNT_NUMERIC": 0.02,
            }
        ]
    }
    monkeypatch.setattr(
        prepare_data.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _response(payload),
    )

    with pytest.raises(ValueError, match="WHO GHE OData response failed schema"):
        prepare_data._who_ghe_get({"$top": 1})


def test_who_ingestion_retains_pagination_metadata(monkeypatch) -> None:
    payload = {
        "@odata.context": "https://example.invalid/context",
        "@odata.nextLink": "https://example.invalid/next",
        "value": [
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
        ],
    }
    monkeypatch.setattr(
        prepare_data.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _response(payload),
    )

    page = prepare_data._who_ghe_get({"$top": 1})
    assert page.next_link == "https://example.invalid/next"
    assert page.value[0]["DIM_COUNTRY_CODE"] == "USA"
