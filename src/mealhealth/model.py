# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Core health-impact calculation engine.

Implements the formulas in ``docs/methodology.md``:

* ``RR_{r,d}(x)`` read off the GBD dose-response curve by log-linear
  interpolation;
* ``RR_d(x) = prod_r RR_{r,d}(x_r)`` over risk factors affecting cause ``d``;
* ``PAF_d(x) = 1 - RR_d(x) / RR_d(x_base)`` relative to the baseline diet;
* population ``dYLL`` summed over exact country/age/sex burden strata, for both
  local-life-table and GBD-standard YLL anchors;
* individual (median / given age) expected remaining-lifetime YLL averaged over
  the starting-age sex composition and evaluated with sex-specific survival and
  mortality. Local YLL uses sex-specific remaining life expectancy; standard
  YLL uses the common GBD theoretical-minimum-risk life table.

Positive ``dYLL`` = years gained (burden reduced); negative = years lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Literal

import numpy as np
import pandas as pd

from . import data
from .foodgroups import (
    ADULT_AGES,
    AGE_SPAN,
    AGE_START,
    CAUSES,
    DIRECT_NUTRIENT_FACTORS,
    MEDIATOR_FACTORS,
    RISK_FACTORS,
    age_to_bucket,
)
from .sodium import MEDIATED_CURVE_BY_CAUSE, SodiumMeanShiftModel

# --------------------------------------------------------------------------
# Relative-risk curves
# --------------------------------------------------------------------------


class RelativeRiskCurves:
    """Age-specific GBD dose-response curves with log-linear interpolation."""

    def __init__(self, rr_df: pd.DataFrame | None = None):
        if rr_df is None:
            rr_df = data.relative_risks()
        self._curve: dict[tuple[str, str, str], tuple[np.ndarray, np.ndarray]] = {}
        self.pairs: set[tuple[str, str]] = set()
        for (risk, cause, age), grp in rr_df.groupby(["risk_factor", "cause", "age"]):
            grp = grp.sort_values("exposure_g_per_day")
            x = grp["exposure_g_per_day"].to_numpy(dtype=float)
            log_rr = np.log(grp["rr_mean"].to_numpy(dtype=float))
            self._curve[(risk, cause, age)] = (x, log_rr)
            self.pairs.add((risk, cause))

    def log_rr(self, risk: str, cause: str, age: str, intake: float) -> float:
        """Interpolate log(RR) at ``intake`` (clamped to the data range)."""
        x, log_rr = self._curve[(risk, cause, age)]
        if intake <= x[0]:
            return float(log_rr[0])
        if intake >= x[-1]:
            return float(log_rr[-1])
        return float(np.interp(intake, x, log_rr))

    def causes_for(self, risk: str) -> list[str]:
        return [c for c in CAUSES if (risk, c) in self.pairs]


# --------------------------------------------------------------------------
# Per-country burden
# --------------------------------------------------------------------------


LifeTableKind = Literal["local", "standard"]
SEXES = ("male", "female")


class CountryBurden:
    """Burden inputs for one country: baseline diet, mortality, life table."""

    def __init__(self, country: str):
        self.country = country
        countries = set(data.available_countries())
        if country not in countries:
            raise KeyError(
                f"No bundled data for country {country!r}. "
                f"Use mealhealth.list_countries() to see the {len(countries)} "
                "available ISO3 codes."
            )

        bi = data.baseline_intake()
        self.baseline: dict[str, float] = dict(
            bi.loc[
                bi["country"] == country, ["risk_factor", "intake_g_per_day"]
            ].itertuples(index=False, name=None)
        )
        bn = data.baseline_nutrients()
        nutrient_baseline = dict(
            bn.loc[
                bn["country"] == country, ["nutrient", "intake_g_per_day"]
            ].itertuples(index=False, name=None)
        )
        missing_nutrients = set(DIRECT_NUTRIENT_FACTORS) - set(nutrient_baseline)
        if missing_nutrients:
            raise ValueError(
                f"Bundled nutrient baseline missing {country}: "
                f"{sorted(missing_nutrients)}"
            )
        self.baseline.update(nutrient_baseline)
        cal = data.baseline_calories()
        self.baseline_kcal = float(
            cal.loc[cal["country"] == country, "kcal_per_day"].iloc[0]
        )

        mort = data.mortality()
        mort = mort[mort["country"] == country]
        self.death_rate: dict[tuple[str, str, str], float] = {
            (r.sex, r.cause, r.age): r.death_rate_per_1000 / 1000.0
            for r in mort.itertuples(index=False)
        }
        pop = data.population()
        pop = pop[pop["country"] == country]
        self.population: dict[tuple[str, str], float] = {
            (row.sex, row.age): row.population
            for row in pop.loc[pop["age"] != "all-a"].itertuples(index=False)
        }

        local_lt = data.local_life_table()
        local_lt = local_lt[local_lt["country"] == country]
        self.local_lx: dict[tuple[str, str], float] = {
            (row.sex, row.age): row.lx for row in local_lt.itertuples(index=False)
        }
        self.local_ex: dict[tuple[str, str], float] = {
            (row.sex, row.age): row.ex for row in local_lt.itertuples(index=False)
        }
        standard_lt = data.standard_life_table()
        self.standard_ex: dict[str, float] = dict(
            standard_lt[["age", "ex"]].itertuples(index=False, name=None)
        )

        self._total_yll_local = self._compute_total_yll(life_table="local")
        self._total_yll_standard = self._compute_total_yll(life_table="standard")
        self._age_weights_local = self._compute_age_weights(life_table="local")
        self._age_weights_standard = self._compute_age_weights(life_table="standard")

    # -- population-mode anchors ------------------------------------------

    def yll_by_stratum(
        self, cause: str, age: str, sex: str, *, life_table: LifeTableKind
    ) -> float:
        """Observed cause-d YLL in an age band = deaths . remaining life exp."""
        m = self.death_rate.get((sex, cause, age), 0.0)
        pop = self.population.get((sex, age), 0.0)
        ex = (
            self.local_ex.get((sex, age), 0.0)
            if life_table == "local"
            else self.standard_ex.get(age, 0.0)
        )
        return m * pop * ex

    def yll_by_cause_age(
        self, cause: str, age: str, *, life_table: LifeTableKind
    ) -> float:
        return sum(
            self.yll_by_stratum(cause, age, sex, life_table=life_table) for sex in SEXES
        )

    def _compute_total_yll(self, *, life_table: LifeTableKind) -> dict[str, float]:
        """Y_d: total observed YLL for each cause (all ages)."""
        out: dict[str, float] = {}
        for cause in CAUSES:
            out[cause] = sum(
                self.yll_by_stratum(cause, age, sex, life_table=life_table)
                for sex in SEXES
                for age in AGE_SPAN
            )
        return out

    def total_yll(self, cause: str, *, life_table: LifeTableKind) -> float:
        totals = (
            self._total_yll_local if life_table == "local" else self._total_yll_standard
        )
        return totals[cause]

    def _compute_age_weights(
        self, *, life_table: LifeTableKind
    ) -> dict[tuple[str, str], float]:
        """w_{a,d} = YLL_{a,d} / sum_a YLL_{a,d} over adult ages."""
        out: dict[tuple[str, str], float] = {}
        for cause in CAUSES:
            ylls = {
                a: self.yll_by_cause_age(cause, a, life_table=life_table)
                for a in ADULT_AGES
            }
            total = sum(ylls.values())
            for a in ADULT_AGES:
                out[(cause, a)] = (
                    ylls[a] / total if total > 0 else 1.0 / len(ADULT_AGES)
                )
        return out

    def age_weight(self, cause: str, age: str, *, life_table: LifeTableKind) -> float:
        weights = (
            self._age_weights_local
            if life_table == "local"
            else self._age_weights_standard
        )
        return weights[(cause, age)]

    # -- individual-mode helpers ------------------------------------------

    def median_adult_age(self) -> float:
        """Population-weighted median age among adults (25+)."""
        ages = [
            age
            for age in ADULT_AGES
            if sum(self.population.get((sex, age), 0.0) for sex in SEXES) > 0
        ]
        weights = np.array(
            [
                sum(self.population.get((sex, age), 0.0) for sex in SEXES)
                for age in ages
            ],
            dtype=float,
        )
        mids = np.array([AGE_START[a] + AGE_SPAN.get(a, 5.0) / 2.0 for a in ages])
        order = np.argsort(mids)
        mids, weights = mids[order], weights[order]
        cum = np.cumsum(weights)
        half = cum[-1] / 2.0
        return float(mids[np.searchsorted(cum, half)])

    def sex_weights(self, age: str) -> dict[str, float]:
        populations = {sex: self.population.get((sex, age), 0.0) for sex in SEXES}
        total = sum(populations.values())
        if total <= 0:
            return {sex: 1.0 / len(SEXES) for sex in SEXES}
        return {sex: value / total for sex, value in populations.items()}

    def conditional_survival(self, sex: str, age: str, a0_bucket: str) -> float:
        """S(age | a0): probability of reaching ``age`` given alive at a0."""
        l0 = self.local_lx.get((sex, a0_bucket), 0.0)
        return self.local_lx.get((sex, age), 0.0) / l0 if l0 > 0 else 0.0

    def age_span_years(self, sex: str, age: str) -> float:
        """Width of an age band; the open 95+ interval uses its life exp."""
        if age == "95+":
            return self.local_ex.get((sex, "95+"), 3.0)
        return AGE_SPAN[age]


# --------------------------------------------------------------------------
# Diet construction
# --------------------------------------------------------------------------


@dataclass
class SubstitutedDiet:
    """Baseline scaled by ``f`` with the meal added, in factor exposures."""

    f: float
    exposure: dict[str, float]
    baseline_exposure: dict[str, float]
    warnings: list[str] = field(default_factory=list)


def build_substituted_diet(
    burden: CountryBurden,
    meal: dict[str, float],
    meal_kcal: float,
    risk_factors: tuple[str, ...],
) -> SubstitutedDiet:
    """Construct ``x_r = f . baseline_r + meal_r`` with ``f`` clamped to [0, 1]."""
    warnings: list[str] = []
    if meal_kcal < 0:
        raise ValueError("meal_kcal must be non-negative")
    c_base = burden.baseline_kcal
    f = (c_base - meal_kcal) / c_base
    if f <= 0:
        warnings.append(
            f"Meal energy ({meal_kcal:.0f} kcal) >= baseline daily energy "
            f"({c_base:.0f} kcal); the meal is treated as the entire day's diet "
            "(baseline scale f = 0)."
        )
        f = 0.0

    baseline_exp = {r: float(burden.baseline.get(r, 0.0)) for r in risk_factors}
    exposure = {r: f * baseline_exp[r] + float(meal.get(r, 0.0)) for r in risk_factors}
    return SubstitutedDiet(f, exposure, baseline_exp, warnings)


# --------------------------------------------------------------------------
# Relative-risk aggregation
# --------------------------------------------------------------------------


def _population_log_rr(
    curves: RelativeRiskCurves,
    burden: CountryBurden,
    risk: str,
    cause: str,
    intake: float,
    *,
    life_table: LifeTableKind,
) -> float:
    """YLL-weighted effective log(RR) across adult ages."""
    return sum(
        burden.age_weight(cause, age, life_table=life_table)
        * curves.log_rr(risk, cause, age, intake)
        for age in ADULT_AGES
    )


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


@dataclass
class CauseResult:
    cause: str
    paf_local: float  # 1 - RR(x)/RR(xbase); >0 means burden reduced
    delta_yll_local: float  # years gained (>0) or lost (<0)
    rr_baseline_local: float
    rr_meal_local: float
    paf_standard: float = 0.0
    delta_yll_standard: float = 0.0
    rr_baseline_standard: float = 1.0
    rr_meal_standard: float = 1.0

    @property
    def paf(self) -> float:
        """Alias for :attr:`paf_local`."""
        return self.paf_local

    @property
    def delta_yll(self) -> float:
        """Alias for :attr:`delta_yll_local`."""
        return self.delta_yll_local

    @property
    def rr_baseline(self) -> float:
        """Alias for :attr:`rr_baseline_local`."""
        return self.rr_baseline_local

    @property
    def rr_meal(self) -> float:
        """Alias for :attr:`rr_meal_local`."""
        return self.rr_meal_local


@dataclass
class MealAssessment:
    country: str
    mode: str
    delta_yll_local_total: float
    causes: dict[str, CauseResult]
    risk_attribution_local: dict[str, float]
    f: float
    meal_kcal: float
    baseline_kcal: float
    exposure: dict[str, float]
    baseline_exposure: dict[str, float]
    warnings: list[str]
    relative_only: bool
    age: float | None = None
    delta_yll_standard_total: float = 0.0
    risk_attribution_standard: dict[str, float] = field(default_factory=dict)

    @property
    def delta_yll_total(self) -> float:
        """Alias for :attr:`delta_yll_local_total`."""
        return self.delta_yll_local_total

    @property
    def risk_attribution(self) -> dict[str, float]:
        """Alias for :attr:`risk_attribution_local`."""
        return self.risk_attribution_local

    @property
    def delta_paf_local_total(self) -> dict[str, float]:
        """Per-cause local-weighted PAF relative to the baseline diet."""
        return {c: r.paf_local for c, r in self.causes.items()}

    @property
    def delta_paf_standard_total(self) -> dict[str, float]:
        """Per-cause standard-weighted PAF relative to the baseline diet."""
        return {c: r.paf_standard for c, r in self.causes.items()}

    @property
    def delta_paf_total(self) -> dict[str, float]:
        """Alias for :attr:`delta_paf_local_total`."""
        return self.delta_paf_local_total

    def summary(self) -> str:
        verb = "gained" if self.delta_yll_local_total >= 0 else "lost"
        lines = [
            f"Meal health assessment — {self.country} ({self.mode} mode)",
        ]
        if not self.relative_only:
            lines.append(
                f"  Local-life-table effect of eating this meal daily for life: "
                f"{abs(self.delta_yll_local_total):.4g} years of life {verb} "
                + (
                    "(population-annual YLL)"
                    if self.mode == "population"
                    else "(per person, lifetime)"
                )
            )
            standard_verb = "gained" if self.delta_yll_standard_total >= 0 else "lost"
            lines.append(
                f"  GBD-standard potential effect: "
                f"{abs(self.delta_yll_standard_total):.4g} years of life "
                f"{standard_verb}"
            )
        lines.append(
            f"  Baseline scale f = {self.f:.3f} "
            f"(meal {self.meal_kcal:.0f} / baseline "
            f"{self.baseline_kcal:.0f} kcal)"
        )
        for c, r in self.causes.items():
            piece = f"    {c:7} PAF {r.paf_local:+.4f}"
            if not self.relative_only:
                piece += (
                    f"  dYLL local {r.delta_yll_local:+.4g}"
                    f"  standard {r.delta_yll_standard:+.4g}"
                )
            lines.append(piece)
        for w in self.warnings:
            lines.append(f"  ! {w}")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def assess(
    meal: dict[str, float],
    meal_kcal: float,
    country: str,
    *,
    mode: str = "population",
    age: float | None = None,
    include_processed_meat: bool = True,
    relative_only: bool = False,
    seafood_omega3_mg: float | None = None,
    sodium_mg: float | None = None,
    curves: RelativeRiskCurves | None = None,
) -> MealAssessment:
    """Evaluate the health impact of eating ``meal`` daily in ``country``.

    See :func:`mealhealth.assess_meal` for the documented public wrapper.
    """
    if mode not in {"population", "median", "age"}:
        raise ValueError(f"Unknown mode {mode!r}")
    if mode == "age" and age is None:
        raise ValueError("mode='age' requires the age argument (years)")
    requested_age = None
    if mode == "age":
        try:
            requested_age = float(age)
        except (TypeError, ValueError) as exc:
            raise ValueError("age must be a finite number at least 25") from exc
        if not math.isfinite(requested_age) or requested_age < 25:
            raise ValueError("age must be a finite number at least 25")

    food_risk_factors = tuple(
        r for r in RISK_FACTORS if include_processed_meat or r != "processed_meat"
    )
    unknown = set(meal) - set(RISK_FACTORS)
    if unknown:
        raise ValueError(
            f"Unknown meal food groups: {sorted(unknown)}. "
            f"Valid risk-factor groups: {list(RISK_FACTORS)}. Foods outside "
            "these groups affect the result only via meal_kcal."
        )

    nutrient_amounts: dict[str, float] = {}
    if seafood_omega3_mg is not None:
        try:
            amount = float(seafood_omega3_mg)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "seafood_omega3_mg must be a finite non-negative number"
            ) from exc
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("seafood_omega3_mg must be a finite non-negative number")
        factor = DIRECT_NUTRIENT_FACTORS["omega3"]
        nutrient_amounts["omega3"] = amount * factor.api_to_internal

    sodium_g: float | None = None
    if sodium_mg is not None:
        try:
            amount = float(sodium_mg)
        except (TypeError, ValueError) as exc:
            raise ValueError("sodium_mg must be a finite non-negative number") from exc
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("sodium_mg must be a finite non-negative number")
        sodium_g = amount * MEDIATOR_FACTORS["sodium"].api_to_internal

    direct_risk_factors = food_risk_factors + tuple(nutrient_amounts)
    meal_exposure = {**meal, **nutrient_amounts}

    if curves is None:
        curves = RelativeRiskCurves()
    burden = CountryBurden(country)
    diet = build_substituted_diet(burden, meal_exposure, meal_kcal, direct_risk_factors)
    sodium_model = None
    if sodium_g is not None:
        sodium_model = SodiumMeanShiftModel(country)
        baseline_sodium, meal_sodium = sodium_model.weighted_exposure(
            burden.population,
            baseline_scale=diet.f,
            meal_sodium_g=sodium_g,
        )
        diet.baseline_exposure["sodium"] = baseline_sodium
        diet.exposure["sodium"] = meal_sodium
        diet.warnings.append(
            "Sodium uses a central stratum-mean approximation; it does not model "
            "the within-stratum distribution of sodium or blood pressure."
        )
    risk_factors = direct_risk_factors + (("sodium",) if sodium_model else ())

    if mode == "population":
        causes = _assess_population(
            curves,
            burden,
            diet,
            risk_factors,
            relative_only,
            sodium_model=sodium_model,
            sodium_g=sodium_g,
        )
        a0 = None
    else:
        a0 = burden.median_adult_age() if mode == "median" else requested_age
        causes = _assess_individual(
            curves,
            burden,
            diet,
            risk_factors,
            a0,
            relative_only,
            sodium_model=sodium_model,
            sodium_g=sodium_g,
        )

    delta_local_total = sum(r.delta_yll_local for r in causes.values())
    delta_standard_total = sum(r.delta_yll_standard for r in causes.values())
    attribution_local = _attribute_by_risk(
        curves,
        burden,
        diet,
        risk_factors,
        causes,
        mode,
        a0,
        life_table="local",
        sodium_model=sodium_model,
        sodium_g=sodium_g,
    )
    attribution_standard = _attribute_by_risk(
        curves,
        burden,
        diet,
        risk_factors,
        causes,
        mode,
        a0,
        life_table="standard",
        sodium_model=sodium_model,
        sodium_g=sodium_g,
    )
    return MealAssessment(
        country=country,
        mode=mode,
        delta_yll_local_total=delta_local_total,
        causes=causes,
        risk_attribution_local=attribution_local,
        f=diet.f,
        meal_kcal=meal_kcal,
        baseline_kcal=burden.baseline_kcal,
        exposure=diet.exposure,
        baseline_exposure=diet.baseline_exposure,
        warnings=diet.warnings,
        relative_only=relative_only,
        age=a0,
        delta_yll_standard_total=delta_standard_total,
        risk_attribution_standard=attribution_standard,
    )


def _assess_population(
    curves,
    burden,
    diet,
    risk_factors,
    relative_only,
    *,
    sodium_model=None,
    sodium_g=None,
):
    causes: dict[str, CauseResult] = {}
    for cause in CAUSES:
        relevant = [risk for risk in risk_factors if (risk, cause) in curves.pairs]
        sodium_relevant = sodium_model is not None and (
            cause == "StomachCancer" or cause in MEDIATED_CURVE_BY_CAUSE
        )
        if not relevant and not sodium_relevant:
            continue
        delta = {"local": 0.0, "standard": 0.0}
        for age in ADULT_AGES:
            log_base = sum(
                curves.log_rr(risk, cause, age, diet.baseline_exposure[risk])
                for risk in relevant
            )
            log_meal = sum(
                curves.log_rr(risk, cause, age, diet.exposure[risk])
                for risk in relevant
            )
            direct_risk_ratio = math.exp(log_meal - log_base)
            for sex in SEXES:
                sodium_risk_ratio = (
                    sodium_model.stratum_effect(
                        cause,
                        age,
                        sex,
                        baseline_scale=diet.f,
                        meal_sodium_g=sodium_g,
                    ).risk_ratio
                    if sodium_relevant
                    else 1.0
                )
                risk_ratio = direct_risk_ratio * sodium_risk_ratio
                for life_table in ("local", "standard"):
                    delta[life_table] += burden.yll_by_stratum(
                        cause, age, sex, life_table=life_table
                    ) * (1.0 - risk_ratio)
        total_local = burden.total_yll(cause, life_table="local")
        total_standard = burden.total_yll(cause, life_table="standard")
        paf_local = delta["local"] / total_local if total_local > 0 else 0.0
        paf_standard = delta["standard"] / total_standard if total_standard > 0 else 0.0
        causes[cause] = CauseResult(
            cause=cause,
            paf_local=paf_local,
            delta_yll_local=0.0 if relative_only else delta["local"],
            rr_baseline_local=1.0,
            rr_meal_local=1.0 - paf_local,
            delta_yll_standard=0.0 if relative_only else delta["standard"],
            paf_standard=paf_standard,
            rr_baseline_standard=1.0,
            rr_meal_standard=1.0 - paf_standard,
        )
    return causes


def _assess_individual(
    curves,
    burden,
    diet,
    risk_factors,
    a0,
    relative_only,
    *,
    sodium_model=None,
    sodium_g=None,
):
    a0_bucket = age_to_bucket(a0)
    future_ages = [a for a in ADULT_AGES if AGE_START[a] >= AGE_START[a0_bucket]]
    sex_weights = burden.sex_weights(a0_bucket)
    causes: dict[str, CauseResult] = {}
    for cause in CAUSES:
        relevant = [r for r in risk_factors if (r, cause) in curves.pairs]
        sodium_relevant = sodium_model is not None and (
            cause == "StomachCancer" or cause in MEDIATED_CURVE_BY_CAUSE
        )
        if not relevant and not sodium_relevant:
            continue
        delta_yll_local = 0.0
        delta_yll_standard = 0.0
        # PAF reported at the individual's current age band (for the relative
        # metric); the YLL sum uses the age-specific PAF at each future age.
        risk_ratio_a0 = 0.0
        for age_band in future_ages:
            log_base = sum(
                curves.log_rr(r, cause, age_band, diet.baseline_exposure[r])
                for r in relevant
            )
            log_meal = sum(
                curves.log_rr(r, cause, age_band, diet.exposure[r]) for r in relevant
            )
            direct_risk_ratio = math.exp(log_meal - log_base)
            for sex in SEXES:
                sodium_risk_ratio = (
                    sodium_model.stratum_effect(
                        cause,
                        age_band,
                        sex,
                        baseline_scale=diet.f,
                        meal_sodium_g=sodium_g,
                    ).risk_ratio
                    if sodium_relevant
                    else 1.0
                )
                risk_ratio = direct_risk_ratio * sodium_risk_ratio
                paf_a = 1.0 - risk_ratio
                if age_band == a0_bucket:
                    risk_ratio_a0 += sex_weights[sex] * risk_ratio
                if not relative_only:
                    surv = burden.conditional_survival(sex, age_band, a0_bucket)
                    m = burden.death_rate.get((sex, cause, age_band), 0.0)
                    span = burden.age_span_years(sex, age_band)
                    weight = sex_weights[sex] * surv * (m * span) * paf_a
                    delta_yll_local += weight * burden.local_ex.get(
                        (sex, age_band), 0.0
                    )
                    delta_yll_standard += weight * burden.standard_ex.get(age_band, 0.0)
        paf0 = 1.0 - risk_ratio_a0
        causes[cause] = CauseResult(
            cause=cause,
            paf_local=paf0,
            delta_yll_local=delta_yll_local,
            rr_baseline_local=1.0,
            rr_meal_local=risk_ratio_a0,
            delta_yll_standard=delta_yll_standard,
            paf_standard=paf0,
            rr_baseline_standard=1.0,
            rr_meal_standard=risk_ratio_a0,
        )
    return causes


def _attribute_by_risk(
    curves,
    burden,
    diet,
    risk_factors,
    causes,
    mode,
    a0,
    *,
    life_table: LifeTableKind,
    sodium_model,
    sodium_g,
):
    """Additive decomposition of total dYLL across risk factors.

    Each cause's dYLL is split in proportion to each risk factor's share of the
    total change in log(RR) for that cause (the quantity the PAF is monotone
    in). Shares sum to the cause total exactly (up to the linearisation of the
    log->RR map, which is what the PAF itself uses).
    """
    attribution = dict.fromkeys(risk_factors, 0.0)
    if mode == "population":
        age_bands = [None]
    else:
        a0_bucket = age_to_bucket(a0)
        age_bands = [a for a in ADULT_AGES if AGE_START[a] >= AGE_START[a0_bucket]]

    for cause, res in causes.items():
        cause_delta = (
            res.delta_yll_local if life_table == "local" else res.delta_yll_standard
        )
        if cause_delta == 0.0:
            continue
        # log-RR change per risk (summed/weighted exactly as the cause PAF is).
        contrib: dict[str, float] = {}
        for risk in risk_factors:
            if risk == "sodium":
                d = _sodium_attribution_log_ratio(
                    sodium_model,
                    burden,
                    diet,
                    cause,
                    mode,
                    age_bands,
                    life_table=life_table,
                    sodium_g=sodium_g,
                )
                if d != 0.0:
                    contrib[risk] = d
                continue
            if (risk, cause) not in curves.pairs:
                continue
            if mode == "population":
                d = _population_log_rr(
                    curves,
                    burden,
                    risk,
                    cause,
                    diet.exposure[risk],
                    life_table=life_table,
                ) - _population_log_rr(
                    curves,
                    burden,
                    risk,
                    cause,
                    diet.baseline_exposure[risk],
                    life_table=life_table,
                )
            else:
                d = 0.0
                for ab in age_bands:
                    d += curves.log_rr(
                        risk, cause, ab, diet.exposure[risk]
                    ) - curves.log_rr(risk, cause, ab, diet.baseline_exposure[risk])
            contrib[risk] = d
        total = sum(contrib.values())
        if abs(total) < 1e-15:
            continue
        for risk, d in contrib.items():
            attribution[risk] += (d / total) * cause_delta
    return attribution


def _sodium_attribution_log_ratio(
    sodium_model,
    burden,
    diet,
    cause,
    mode,
    age_bands,
    *,
    life_table,
    sodium_g,
):
    """Effective sodium log-risk change used only for additive attribution."""

    if sodium_model is None or not (
        cause == "StomachCancer" or cause in MEDIATED_CURVE_BY_CAUSE
    ):
        return 0.0
    if mode == "population":
        weighted = 0.0
        total = 0.0
        for age in ADULT_AGES:
            for sex in SEXES:
                yll = burden.yll_by_stratum(cause, age, sex, life_table=life_table)
                ratio = sodium_model.stratum_effect(
                    cause,
                    age,
                    sex,
                    baseline_scale=diet.f,
                    meal_sodium_g=sodium_g,
                ).risk_ratio
                weighted += yll * math.log(ratio)
                total += yll
        return weighted / total if total > 0 else 0.0

    result = 0.0
    for age in age_bands:
        sex_weights = burden.sex_weights(age)
        for sex in SEXES:
            ratio = sodium_model.stratum_effect(
                cause,
                age,
                sex,
                baseline_scale=diet.f,
                meal_sodium_g=sodium_g,
            ).risk_ratio
            result += sex_weights[sex] * math.log(ratio)
    return result
