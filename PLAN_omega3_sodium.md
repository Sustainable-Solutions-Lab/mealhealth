# Plan: add seafood omega-3 (and later sodium) as nutrient risk factors

Status: reviewed design; ready for implementation, but no implementation has
started. The data/metadata claims below were re-verified against the live BoP
tool, the checked-in GBD 2019 workbook, the staged GBD 2023 exposure files, and
the existing code (see the inline "verified/confirmed" annotations); the one
input not machine-checkable here is the exact 0.470-0.660 g/day TMREL, which must
be quoted from the GBD 2023 appendix. Scope: implement seafood omega-3 (EPA +
DHA) now and build a reusable nutrient-factor mechanism. Sodium remains a separate
phase because its mediated outcomes are not a near-drop-in data addition.

## 1. The core idea and why it needs a new concept

Every existing risk factor is a **food group supplied by mass** (`grams` in a
per-group basis). The meal is a `dict[group -> grams]`, and the substituted diet
is `x_r = f·baseline_r + meal_r` where `f = (C_base − C_meal)/C_base`.

Seafood omega-3 and sodium don't fit that shape:

- They are **nutrient contents**, not food-group masses. As the user noted, a
  "seafood" group in grams is inadequate (omega-3 density varies widely), and
  listing individual ingredients explodes. The natural input is **mg of the
  nutrient in the meal**.
- They are **optional**: a caller may not know the meal's omega-3/sodium content.

So we introduce a second *kind* of risk factor — a **nutrient factor** — that
reuses the entire existing engine (RR curve → PAF → ΔYLL, substitution,
attribution) but differs in three respects: input unit (mg), where the baseline
comes from, and optional/omit semantics.

### The one genuinely new semantic: omitted ≠ zero

For a food group, an absent key means the meal contains **0 g** of it — a real
statement. For a nutrient, we must distinguish:

- **Nutrient not supplied (`None`)** → the caller isn't assessing it. The factor
  is **excluded** from this assessment entirely (contributes to no cause,
  baseline and meal both dropped). This is the default and keeps back-compat.
- **Nutrient supplied as a number, including `0.0`** → a real statement ("this
  meal has no seafood omega-3"). It enters the substituted diet normally after
  API-unit conversion: `x = f·baseline + meal_g`. A genuinely zero-omega-3 meal
  that displaces a baseline containing seafood then correctly shows an omega-3
  *deficit* vs baseline and a CHD penalty. This is a feature, not a bug.

This `None`-vs-`0` distinction is the crux of the API design.

## 2. API changes (`api.py`, `model.py::assess`)

Add explicit optional keyword args to `assess_meal` / `assess`:

```python
def assess_meal(meal, meal_kcal, country, *, mode="population", age=None,
                include_processed_meat=True, relative_only=False,
                seafood_omega3_mg: float | None = None,
                ) -> MealAssessment
```

Rationale for explicit kwargs over stuffing nutrients into the `meal` dict:

- `meal` is documented and validated as *grams of food groups*; mixing mg
  nutrients into the same dict conflates units and breaks the "unknown key →
  error" validation that catches typos.
- Explicit kwargs are discoverable, typed, and give the `None`-vs-`0` semantics
  for free via the default.

Do not expose `sodium_mg` until sodium has a defined outcome model and bundled
data: accepting an unsupported argument would invite silent omission. Internally,
collect implemented, non-`None` nutrient kwargs into a small
`nutrient_amounts: dict[str, float]`, convert them through the registry, and merge
them into the internal meal-exposure mapping. Adding a future nutrient should
then require a public kwarg, a registry entry, and data, but no engine rewrite.

Validate every supplied nutrient amount as finite and non-negative. Use the
precise public name `seafood_omega3_mg`: the GBD exposure is specifically
**seafood EPA + DHA**, not total omega-3 or plant ALA. Make that definition
unmissable in the docstring.

`MealAssessment` already carries `exposure` / `baseline_exposure` /
`risk_attribution` as `dict[str, float]`; nutrient factors slot in as extra keys.
`summary()` needs no structural change, but see docs/units note below for
labelling.

## 3. Registry changes (`foodgroups.py`)

`FOOD_GROUPS`/`FoodGroup` is specifically about food groups (mass basis,
human description). Rather than overload it, add a parallel nutrient registry and
a unified risk-factor list the model iterates.

- Add `@dataclass NutrientFactor` with fields `name`, `label`, `api_unit`
  (`"mg"` per meal), `api_to_internal` (`0.001` for mg -> internal g/day when
  the meal is modelled as a daily meal), `description`, and `harmful` (seafood
  omega-3 is protective; sodium will be harmful).
- `NUTRIENT_FACTORS: dict[str, NutrientFactor]` initially contains only the
  implemented seafood omega-3 factor. Do not register sodium before its curves
  and baseline exist.
- Preserve the public meaning of `RISK_FACTORS` as food groups. Add a clearly
  named full-data tuple such as `MODEL_RISK_FACTORS`, while the model builds each
  assessment's active tuple from `RISK_FACTORS + supplied nutrients`. The key
  invariant is that **the model's per-factor loops (curve lookup, substitution,
  attribution) are driven by a single list that includes active nutrients**.
- `harmful` is currently unused by the engine (risk direction is baked into the
  TMREL-clipped curve); keep it for the curve-shape tests and docs only.

The engine (`RelativeRiskCurves`, `build_substituted_diet`, `_assess_*`,
`_attribute_by_risk`) is already keyed on generic `risk` strings and a
`baseline` dict, so **it needs almost no change** beyond being handed the active
factor set (food groups + supplied nutrients) instead of the fixed
`RISK_FACTORS`. Nutrients flow through `build_substituted_diet` once their
baseline and converted meal values are in its internal exposure mapping.

Missing-data policy. `build_substituted_diet` keeps its existing
`baseline.get(r, 0.0)` line unchanged — but that `0.0` default must never fire
for an *active* nutrient, or a missing country baseline would silently become a
real zero exposure. Guarantee that at the data layer rather than by special-casing
the engine: validate the bundled nutrient table at load/build time and raise a
clear data-integrity error if any supported country lacks exactly one finite,
non-negative value per implemented nutrient. Then the key is always present when
the nutrient is active, and the default is unreachable.

Key wiring detail: activeness is decided **only** in `assess()`, by whether
`omega3` is placed in the active factor tuple — never by a `CountryBurden` filter.
When `seafood_omega3_mg` is `None`, `omega3` is absent from that tuple and
contributes nothing (even though its baseline is loaded); when it is a number,
`omega3` is in the tuple and its baseline is pulled from the nutrient baseline
data. `CountryBurden` therefore loads every bundled nutrient baseline
unconditionally — an inactive nutrient's presence in `CountryBurden.baseline` is
harmless because `build_substituted_diet` only iterates the active tuple.

## 4. Unit handling — keep the internal axis in g/day (recommended)

The RR table column is `exposure_g_per_day`; baseline is `intake_g_per_day`.
Recommendation: **keep g/day as the single internal unit everywhere** and convert
at the API boundary only.

- The GBD Burden-of-Proof API reports seafood omega-3 exposure in **g/day**
  (verified against the live tool: `rei_id=121`, cause `493`, `risk_unit="g/day"`,
  a 100-point 0.0-10.8 g/day axis), despite GBD's prose definition commonly being
  written in mg/day. Keep that curve unchanged internally. Convert the user's
  mg-per-meal value by `/1000` before it enters `build_substituted_diet`. Note
  the axis extends to 10.8 g/day, far above any plausible meal or the TMREL clip,
  so real inputs sit well inside the data range (the model also clamps beyond it).
- GBD sodium exposure is also g/day, specifically 24 h urinary sodium, so a
  future sodium input in mg would use the same API conversion.
- User-facing API stays in **mg** for both nutrients (how people think:
  "2300 mg sodium", "250 mg omega-3").

This means **no schema/column rename** to `relative_risks.csv`; omega-3 rows
carry small g/day values, which are internally consistent. Keep the conversion
in `NutrientFactor.api_to_internal` rather than conflating API-unit conversion
with `RR_BASIS_FACTOR`, whose purpose is model-basis conversion for curve data.

## 5. Relative-risk data (`tools/prepare_data.py`)

Seafood omega-3 → **CHD only** in the current BoP manifest (ischemic heart
disease). Verified against the live BoP tool: `rei_id=121`, the risk-cause
manifest maps it to cause `493` (CHD) **only**, `risk_unit="g/day"`, and the
curve is a 100-point 0.0-10.8 g/day axis that is monotonic non-increasing
(protective; RR 1.0 at 0 → ~0.73 plateau). Steps:

1. **IDs**: add `"omega3": 121` to `GBD_REI_ID` and
   `"omega3": ["CHD"]` to `RISK_CAUSE_MAP`. Retain the manifest check so an
   upstream change fails explicitly.
2. **Unit check**: no fetcher relaxation and no `RR_BASIS_FACTOR["omega3"]` are
   needed: BoP already serves this risk in `g/day`. Keep the existing strict
   `g/day` assertion. The `/1000` conversion belongs only at the public API
   boundary and in the nutrient-baseline builder.
3. **TMREL** (`tools/reference/rr_tmrel.csv`): add
   `omega3,protective,0.470,0.660,GBD 2023 appendix 2 section 4`.
   GBD 2023 retains the 470-660 mg/day range, but this CSV follows the BoP/model
   curve's **g/day** unit. Do not apply a basis factor to this row. With
   `RR_BASIS_FACTOR["omega3"]` absent (=1.0), `build_relative_risks` clips at the
   midpoint `0.5·(0.470+0.660) = 0.565 g/day`. This is consistent with the actual
   BoP curve, which realizes most of its protective RR reduction (1.0 → ~0.74) by
   ~0.66 g/day and plateaus (~0.727) beyond ~1 g/day — so the clip sits on the
   knee of the curve, as a TMREL should. The exact 0.470-0.660 endpoints are the
   one input not machine-verifiable here; quote them from the GBD 2023 appendix
   (this row's `source` field records the citation).
4. **Age attenuation** (`rr_age_attenuation.csv`): regenerate through
   `tools/generate_rr_age_attenuation.py` by adding
   `"Diet low in seafood omega-3 fatty acids": "omega3"` to `GBD_RISK_NAMES`
   and `"omega3": ["CHD"]` to `NEEDED`. **Verified in the checked-in GBD 2019
   workbook**: the "Diet low in seafood omega-3 fatty acids" block contains only
   Ischemic-heart-disease rows, its exposures are written in **g/day**
   (`0`, `0.1`, ... `0.4 g/day`, so the parser's `g/day` regex matches with no
   change), and all 15 adult age columns are populated. The derived age shape is
   real and distinct from `fruits->CHD` — it amplifies young ages (`beta ≈ 1.8`
   at 25-29) and attenuates old ages (`beta ≈ 0.75` at 95+) relative to the 60-64
   reference — so there is no reason to copy another risk's beta column.
5. **Cache completeness**: `data/raw/bop_rr_curves.csv` already exists and
   predates omega-3 (**confirmed**: the cached file holds 17 `(risk, cause)`
   pairs, none for omega-3). Merely adding the ID will leave `_load_bop_curves()`
   reading an incomplete cache. Either delete/refetch the cache during
   regeneration or,
   preferably, validate cached `(risk, cause)` pairs against `RISK_CAUSE_MAP`
   and refetch/fail with an actionable message when incomplete.
6. `build_relative_risks` itself needs no further structural change — omega-3
   flows through `_load_bop_curves` → basis convert → `_clip_at_tmrel`
   (protective) → `_thin` → `_age_expand` like any protective factor. It is
   **not** in `ALTERNATIVE_RR`.

## 6. Baseline nutrient data (baseline diet side)

The current baseline (`baseline_intake.csv`) is food-group grams from
GLADE/GDD-IA and has no nutrient rows. A per-country seafood EPA+DHA baseline is
needed whenever that optional factor is active. Use the official **GBD 2023
Dietary Risk Exposure Estimates**, not GDD. This matches the GBD exposure concept
and vintage used by the RR curve and removes any operational dependency on
GLADE.

### 6.1 Raw-data acquisition and local layout

Raw inputs are build-time-only, non-redistributed files under the already
git-ignored `data/raw/`. Ordinary installation or wheel/sdist construction uses
the committed processed CSV and does **not** require these downloads; they are
needed only to regenerate `baseline_nutrients.csv`.

For current development, bootstrap the files from the sibling GLADE checkout:

```bash
mkdir -p data/raw/IHME_GBD_2023_RISK_EXPOSURE_DIET_1
mkdir -p data/raw/IHME_GBD_2023_RISK_EXPOSURE_DIET_2
cp \
  ../GLADE/data/manually_downloaded/IHME_GBD_2023_RISK_EXPOSURE_DIET_1/IHME_GBD_2023_RISK_EXPOSURE_DIET_HIGH_IN_SODIUM_Y2025M10D10.CSV \
  data/raw/IHME_GBD_2023_RISK_EXPOSURE_DIET_1/
cp \
  ../GLADE/data/manually_downloaded/IHME_GBD_2023_RISK_EXPOSURE_DIET_2/IHME_GBD_2023_RISK_EXPOSURE_DIET_LOW_IN_SEAFOOD_OMEGA_3_FATTY_ACIDS_Y2025M10D10.CSV \
  data/raw/IHME_GBD_2023_RISK_EXPOSURE_DIET_2/
```

This copy is a convenience, not a source-code or workflow dependency. A new
checkout must be reproducible without GLADE. Add the following complete manual
acquisition instructions to `docs/data_sources.md`:

1. Create or sign in to a free IHME account.
2. Open the GBD 2023 Dietary Risk Exposure Estimates record:
   <https://ghdx.healthdata.org/record/ihme-data/gbd-2023-dietary-risk-exposure-estimates>.
3. Download both authenticated archives:
   - [`IHME_GBD_2023_RISK_EXPOSURE_DIET_1.zip`](https://ghdx.healthdata.org/sites/default/files/record-attached-files/IHME_GBD_2023_RISK_EXPOSURE_DIET_1.zip)
   - [`IHME_GBD_2023_RISK_EXPOSURE_DIET_2.zip`](https://ghdx.healthdata.org/sites/default/files/record-attached-files/IHME_GBD_2023_RISK_EXPOSURE_DIET_2.zip)
   The direct links redirect to IHME login unless the browser session is already
   authenticated; the builder must not attempt to download them.
4. Extract them so the checkout contains exactly:
   - `data/raw/IHME_GBD_2023_RISK_EXPOSURE_DIET_1/`
   - `data/raw/IHME_GBD_2023_RISK_EXPOSURE_DIET_2/`
5. For this release, verify these source files:
   - `...DIET_1/IHME_GBD_2023_RISK_EXPOSURE_DIET_HIGH_IN_SODIUM_Y2025M10D10.CSV`
   - `...DIET_2/IHME_GBD_2023_RISK_EXPOSURE_DIET_LOW_IN_SEAFOOD_OMEGA_3_FATTY_ACIDS_Y2025M10D10.CSV`

Pin exact filenames and SHA-256 checksums in the builder so an upstream release
change is intentional rather than silently selected by a broad glob. The checked
development copies have these hashes:

- sodium: `0ea88321aba71f3c4cba0ca02472928ff06c78600e3a0a182bae4588217d23fd`
- seafood omega-3: `4e80f1047b13251d674da636d6cce35cb56b64878e79774c59f927d569d9b28f`

The archives require an authenticated browser download and must not be fetched
automatically. Document the IHME Free-of-Charge Non-commercial User Agreement
and cite: *Global Burden of Disease Collaborative Network. Global Burden of
Disease Study 2023 (GBD 2023) Dietary Risk Exposure Estimates. IHME, 2025.*

### 6.2 Mealhealth-owned deterministic builder

Add a standalone `tools/build_baseline_nutrients_from_gbd.py`. It reads only
paths under this checkout and must not import GLADE modules or consume GLADE
processing outputs. Its inputs are:

- the two exposure directories above (omega-3 is in archive 2; the sodium file
  is staged for phase 2);
- `data/raw/IHME-GBD_2023-death-rates-2020.csv`, already required by
  `prepare_data.py`, as the canonical set of national GBD `location_id` values;
- `data/raw/WPP_population.csv.gz`, already downloaded by `prepare_data.py`, for
  exact sex- and age-specific population weights.

For seafood omega-3, the builder must:

1. Validate the exact raw schema, checksum, `measure_id=19`,
   `measure="continuous"`, available years 1990-2023, both sexes, and all
   required adult age groups. **Verified in the checked development copy**:
   columns `age_group_id, age_group_name, sex_id, sex, year_id, location_id,
   location_name, measure_id, measure, mean, lower, upper`; `measure_id=19`,
   `measure="continuous"`; 34 years 1990-2023; `sex_id` is `{1,2}` (Male, Female)
   with **no "Both" aggregate row**; and there is **no unit column**. Because the
   unit is not in the file, bind the exact risk token to its documented g/day
   exposure basis in the pinned source specification rather than inferring units
   from value magnitudes.
2. Select the reference year 2020 and national locations only. Filter by
   `location_id`, not `location_name`, because the archives contain colliding
   subnational names such as Georgia.
3. Select the 15 adult groups from 25-29 through 95+. Map GBD age IDs explicitly;
   do not use `All Ages` or `Age-standardized`, which include the under-25
   population for whom these adult dietary risks are not evaluated.
4. Population-weight every age-sex cell using WPP 2020 `PopMale` and
   `PopFemale`. Combine WPP's `95-99` and `100+` populations for the GBD `95+`
   exposure. The sex weighting is **required, not optional**: the raw file
   carries only per-sex (`Male`/`Female`) exposures and no "Both" aggregate, so
   the two must be combined, and a population weighting is preferable to an
   unweighted mean of the two sexes.
5. Retain the GBD mean exposure in g/day. Validate `lower <= mean <= upper`, but
   do not bundle weighted uncertainty bounds because the model does not propagate
   exposure uncertainty and averaging interval endpoints is not a rigorous
   aggregate uncertainty calculation.
6. Map GBD national locations to ISO3 using the same overrides as
   `prepare_data.py`. The raw exposure covers 174 of the package's 175 countries
   directly; fill only `GUF` from the existing documented `GUF -> FRA` proxy.
   **Verified**: French Guiana appears in neither the exposure file nor the
   death-rate CSV (it is not a separate GBD national location), so `GUF` is the
   sole proxy; and all 204 national locations in the death-rate CSV (the canonical
   national set below) are present in the omega-3 exposure file.
7. Write a byte-stable, country-sorted output and fail on duplicates, missing
   weights, missing countries, non-finite values, negative values, or unexpected
   source structure.

The builder should be structured around a small per-nutrient source specification
so sodium can reuse it later, but the committed file initially contains only the
implemented `omega3` factor. The sodium CSV may be copied and checksum-validated
now; do not turn its urinary-sodium exposure into an active meal nutrient until
the dietary-intake-to-urinary-excretion mapping is designed.

### 6.3 Bundled output and runtime loading

Keep `baseline_intake.csv` for food-group grams and add
`baseline_nutrients.csv` with:

```text
country,nutrient,intake_g_per_day,source_country,source_year
USA,omega3,0.3110668,USA,2020
GUF,omega3,0.5444630,FRA,2020
```

`source_country` makes proxy use explicit; `source_year` guards against an
accidental vintage change. `data.py` gains a cached `baseline_nutrients()`
loader, and `CountryBurden` merges **all** bundled nutrient baselines into its
baseline dictionary unconditionally (see §3: a nutrient contributes only when
`assess()` puts it in the active factor tuple, so an unused baseline key is
inert and `build_substituted_diet` stays unchanged). Add build- and load-time
assertions for exactly one finite, non-negative omega-3 value per supported
country. Missing active nutrient data must raise rather than default to zero.

Document the output schema, units, source release, aggregation, sole proxy,
checksums, licence and citation in `docs/data_sources.md` and
`DATA_PROVENANCE.md`. Unlike `baseline_intake.csv` and
`baseline_calories.csv`, this nutrient baseline is directly reproducible from
official GBD and WPP inputs and is not part of the temporary GLADE/Zenodo
baseline-diet handoff.

## 7. Documentation

- `docs/methodology.md`: the current out-of-scope caveat (the bullet at
  "Additional dietary risk factors (sodium, sugar-sweetened beverages) are
  **not** modelled…") names **sodium and SSBs — not omega-3**, so there is no
  omega-3 caveat to delete; instead narrow that bullet to keep only sodium/SSB as
  future scope. Add a short "Nutrient factors" subsection explaining the mg input,
  the omitted-vs-zero semantics, and that seafood omega-3→CHD reuses the same
  PAF→ΔYLL machinery. Update the §5 cause/risk-factor table to add omega-3→CHD.
- `docs/food_groups.md`: add a "Nutrient inputs" section for seafood omega-3
  with units (mg per meal), the EPA+DHA definition, optional semantics, and
  typical ranges. Clarify it is *not* a mass-basis food group and excludes ALA.
- `docs/usage.md`: add an example call passing `seafood_omega3_mg=...`.
- `AGENTS.md`: note nutrient factors in the design-decisions section and the
  new baseline nutrient dataset.
- `README.md`: brief mention if it enumerates risk factors.

## 8. Tests

- `test_curves.py::test_bundled_data_present`: currently asserts
  `set(rr["risk_factor"]) == set(RISK_FACTORS)`. Update to the new full factor
  set (food groups + nutrients). Add omega-3 to the protective-curve monotonicity
  test.
- `test_cause_maps_match_gbd`: add `omega3 → {CHD}`.
- `test_assessment.py`: add cases —
  - the omitted/default call has no omega-3 exposure or attribution key and
    preserves a checked pre-feature result (calling once with the omitted kwarg
    and once with explicit `None` alone is not an independent regression guard).
  - omega-3 supplied high (e.g. a salmon meal) → CHD PAF improves vs baseline.
  - omega-3 supplied `0.0` in a meal that displaces a seafood-containing baseline
    → CHD penalty (the omitted≠zero distinction).
- `test_substitution.py`: nutrient enters `x = f·baseline + meal_mg/1000`
  correctly; unit conversion boundary is exercised.
- Add focused tests for `build_baseline_nutrients_from_gbd.py` using tiny
  synthetic GBD/WPP fixtures: exact age-sex weighting, 95+ population folding,
  national-location filtering, GUF proxy provenance, checksum/schema failures,
  deterministic row order and byte-identical repeated output.
- Add a bundled-data assertion for all 175 countries, `source_year == 2020`, and
  `source_country == country` except `GUF -> FRA`.
- Add rejection tests for negative, NaN and infinite nutrient amounts, plus a
  data-integrity test proving a missing country nutrient baseline raises rather
  than becoming zero.
- Add a handcalc-style omega-3 PAF check at known curve knots in both population
  and individual mode; this is more robust than sign-only integration tests.
- Add regeneration tests/checks for BoP metadata (`rei_id=121`, CHD only,
  `g/day`), cache completeness, TMREL clipping at 0.565 g/day, and all 15
  age-attenuation rows.

## 9. Sodium — phase 2, open questions to resolve first

Sodium is deliberately deferred because it is **not** a clean drop-in, unlike
omega-3:

- **Mediated pathway / units**: GBD models sodium via 24h urinary sodium (g/day)
  with the CVD effect mediated through systolic blood pressure. Must confirm the
  Burden-of-Proof tool serves usable **direct** sodium→outcome dose-response
  curves (and for which outcomes) rather than only the SBP-mediated components.
- **Outcome set may expand `CAUSES`**: sodium's GBD outcomes include stomach
  cancer, CKD, and hypertensive heart disease in addition to
  CHD/Stroke. Options: (i) restrict to the CHD/Stroke curves already in our
  CAUSES set, or (ii) add new causes — which then also needs matching
  **mortality** rows (`mortality.csv` / the GBD Results query) and cause maps.
  This is the main scope driver for sodium and should be an explicit decision.
- **TMREL / direction**: harmful; add a curated `rr_tmrel.csv` row (GBD sodium
  TMREL ~1–5 g/day sodium — confirm exact appendix value).
- **Baseline**: the GBD 2023 sodium exposure CSV is the correct source-side
  baseline and is staged by the acquisition instructions above. It measures
  24-hour urinary sodium. Do not add dietary meal sodium directly to it; first
  define and validate the dietary-intake-to-urinary-excretion transformation.
- The registry, API conversion, optional semantics and engine wiring can be
  reused from omega-3 once those sodium-specific questions are resolved.

## 10. Decisions index

Quick reference to where each settled decision is specified above (not restated
here): public name `seafood_omega3_mg` = EPA+DHA, excludes ALA (§2); separate
`baseline_nutrients.csv` storage (§6.3); baseline source = GBD
2023 Dietary Risk Exposure Estimates via a mealhealth-owned builder (§6);
omega-3-specific age attenuation regenerated from the GBD 2019 workbook (§5.4).

The only decisions still **open** are sodium-specific and belong to phase 2
(§9): whether to restrict sodium to already-supported direct curves or expand
`CAUSES` + mortality data to its full GBD outcome set, and the
dietary-intake-to-urinary-excretion conversion.

## 11. Suggested implementation order

1. Stage the two GBD exposure directories under `data/raw/` (copy from GLADE for
   current development; authenticated IHME download for an independent rebuild)
   and verify the pinned filenames/checksums. This is data staging only.
2. Add the standalone GBD nutrient-baseline builder and its synthetic aggregation
   tests; generate and validate `baseline_nutrients.csv` for omega-3.
3. Registry + engine wiring for a generic nutrient factor with
   unit tests using a synthetic curve — proves the `None`/`0`/exclude semantics.
4. Omega-3 RR data: add the verified BoP ID/pair, g/day TMREL, cache validation
   and generated age attenuation; regenerate `relative_risks.csv`; run curve tests.
5. Add the nutrient-baseline loader and `CountryBurden` merge with strict coverage
   checks.
6. Add `seafood_omega3_mg` to the API and `assess` wiring; input validation,
   assessment tests and docs.
7. (Phase 2) sodium, after the exposure-conversion and outcome-scope decisions.
