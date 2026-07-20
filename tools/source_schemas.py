# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Strict schemas for JSON received from external data-source APIs."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from typing_extensions import TypedDict


class BopCurveMetadata(TypedDict):
    """Fields consumed from one IHME Burden-of-Proof metadata response."""

    risk_unit: str
    star_rating: int
    risk_lower: float
    risk_upper: float


class BopCurvePoint(TypedDict):
    """Fields consumed from one IHME Burden-of-Proof curve point."""

    risk: float
    linear_cause: float
    linear_cause_lower: float
    linear_cause_upper: float


class WhoGheRow(TypedDict):
    """Selected fields in one WHO Global Health Estimates OData row."""

    DIM_COUNTRY_CODE: str
    DIM_YEAR_CODE: int
    DIM_AGEGROUP_CODE: str
    DIM_SEX_CODE: str
    DIM_GHECAUSE_CODE: int
    DIM_GHECAUSE_TITLE: str
    ATTR_POPULATION_NUMERIC: float
    VAL_DTHS_RATE100K_NUMERIC: float
    VAL_DTHS_COUNT_NUMERIC: float


class WhoGhePage(BaseModel):
    """Validated WHO OData page, retaining its optional pagination link."""

    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    value: list[WhoGheRow]
    next_link: str | None = Field(default=None, alias="@odata.nextLink")


BOP_RISK_CAUSE_MANIFEST_ADAPTER = TypeAdapter(dict[str, list[int]])
BOP_CURVE_METADATA_ADAPTER = TypeAdapter(BopCurveMetadata)
BOP_CURVE_ADAPTER = TypeAdapter(list[BopCurvePoint])
WHO_GHE_PAGE_ADAPTER = TypeAdapter(WhoGhePage)

Validated = TypeVar("Validated")


def validate_json_response(
    payload: bytes,
    adapter: TypeAdapter[Validated],
    *,
    source: str,
) -> Validated:
    """Validate response bytes strictly and add source context to any error."""

    try:
        return adapter.validate_json(payload, strict=True)
    except ValidationError as exc:
        raise ValueError(f"{source} response failed schema validation: {exc}") from exc
