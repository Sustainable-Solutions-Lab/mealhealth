<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Design: a GLADE-independent baseline diet

Status: reviewed design; ready for implementation after the seven additional
GBD dietary-exposure files are staged under `data/raw/`. Reviewed against the
implemented sodium mean-shift model on `master` at `ab5824a`. This document
covers the eight factors that use direct country-level baselines, the calorie
anchor, and the integration boundary with sodium's existing stratum-resolved
mediator baseline.

The public assessment API remains unchanged by this work. The one deliberate
input-contract correction is that processed meat becomes grams of product as
eaten, rather than a notional raw-retail equivalent; section 4 explains why.

## 1. Summary

Replace the two current direct-baseline files,
`baseline_intake.csv` and `baseline_nutrients.csv`, with one
`baseline_exposure.csv` containing:

- the seven food-group risk factors; and
- seafood EPA+DHA (`omega3`).

All eight country baselines come from the 2020 means in the official GBD 2023
Dietary Risk Exposure Estimates, aggregated over adults aged 25+ with WPP 2020
age-sex population weights. This aligns the baseline with the exposure
definitions used to interpret the risk curves. It does **not** reproduce a GBD
PAF: `mealhealth` still evaluates each nonlinear curve at a country mean rather
than integrating over GBD's exposure distribution.

`baseline_calories.csv` remains separate. It is rebuilt directly from the
public GDD-IA 2020 calorie file on Zenodo and changes from an all-ages to an
adult-25+ anchor. A checked-in country/source manifest defines the preserved
175-country universe and the baseline exposure/calorie proxy choices. No
builder reads a sibling GLADE checkout.

The implemented `baseline_mediators.csv` remains separate and unchanged in
content. Its builder is migrated from the legacy `baseline_intake.csv` country
anchor to the same manifest. Sodium continues to use country x adult-age x sex
urinary-sodium and SBP means, the existing `sodium_mg` API, and the
sex-resolved burden engine.

GLADE remains methodological provenance: it motivated GBD anchoring, the
country proxies, and several mass-basis conventions. It is not an operational
input to the new workflow.

## 2. Findings from the current checkout

### 2.1 The temporary builder does not use GLADE's anchored diet

`tools/baseline_diet_from_glade.py` reads
`processing/central/dietary_intake.csv`. That is GLADE's source-merged table,
before `estimate_baseline_diet.py` applies GBD precedence. For fruits,
vegetables, legumes and nuts/seeds, the committed values match that
pre-anchoring table to numerical precision. The current US values are the
NHANES override, not GBD exposure.

This is a provenance and reproducibility problem, not proof that GDD-IA is an
invalid intake source. GDD-IA, GBD exposure modelling and food-balance data can
produce materially different intake estimates; the
[published GDD-IA paper](https://doi.org/10.1038/s43016-026-01388-z) shows that
the choice changes comparative-risk results. The reason to select GBD here is
narrower: `mealhealth` is a GBD-oriented health calculation, so using the GBD
exposure definition and vintage for its baseline minimizes a source-definition
mismatch. It should not be presented as knowing the true intake more
accurately.

### 2.2 The current whole-grain artifact is not reproducible from current GLADE

The committed whole-grain column predates GLADE's revised cereal split and no
longer agrees with its current `dietary_intake.csv`. Since the committed CSVs
are canonical, this is not by itself a runtime failure. It does show why a
builder that silently follows a mutable sibling checkout is not an adequate
regeneration contract.

### 2.3 Processed meat is synthesized although GBD publishes it directly

The temporary builder splits GLADE's combined red-meat total with a GDD-IA
processed-meat fraction. GBD 2023 publishes separate unprocessed-red-meat and
processed-meat exposures, and the model already uses separate risk curves.
Using those two published exposures removes both the synthetic split and the
possibility that the baseline definitions overlap.

GLADE omits the GBD processed-meat estimate from its food-system diet because
adding it conflicts with its slaughter-volume mass balance. That constraint is
important for GLADE, but `mealhealth` has no production balance. Here the more
important contract is that a processed-meat curve and its baseline refer to the
same exposure definition. The difference between GBD exposure and physical
food-supply estimates remains a documented source uncertainty; it must not be
described as cancelling from `RR(x) / RR(x_base)`.

### 2.4 Sodium is implemented on a separate baseline path

The sodium implementation establishes a boundary this design must preserve:

- `sodium_mg=None` omits sodium, while `0.0` is an active measured zero;
- `baseline_mediators.csv` contains 175 x 15 adult ages x two sexes = 5,250
  urinary-sodium/SBP rows with uncertainty bounds on each modeled mean;
- `SodiumMeanShiftModel` uses those stratum means and the common caloric
  substitution factor `f`;
- population YLL is summed over exact country x age x sex burden strata, using
  WHO GHE 2021 mortality and sex-specific WPP population/life tables; and
- direct food and omega-3 baselines remain country-level means even though
  their burden is now aggregated over exact age-sex strata.

Sodium must therefore remain outside `baseline_exposure.csv`. Flattening it to
one country mean would discard information used by the runtime. The current
mediator builder still derives its country set from `baseline_intake.csv`; that
is the coupling this design replaces with the canonical manifest.

### 2.5 The existing meat-basis convention is internally inconsistent

`RR_BASIS_FACTOR` currently applies `1.43` to both red and processed meat.
That convention came from converting cooked unprocessed meat to GLADE's raw
retail mass basis. It should not be applied indiscriminately:

- [IHME's dietary-risk methods](https://www.healthdata.org/sites/default/files/methods_appendices/2021/Parent_Diet_GBD2021_updated2023Aug18.pdf)
  define processed-meat exposure as average daily grams of meat preserved by
  smoking, curing, salting or chemical preservatives. There is no single
  meaningful "raw retail" precursor for bacon, ham, sausages and deli meat,
  and no source in the repository supports a universal 1.43 factor.
- The red-meat literature override currently converts the BoP exposure grid to
  raw-retail mass but leaves each literature estimate's `100 g/day` dose unit
  unchanged. That makes the curve 1.43 times too steep if the cited dose is on
  the usual consumed/cooked basis.

The new baseline must not perpetuate those two errors. Section 4 defines the
corrected contract.

## 3. Decisions

1. **Use GBD 2023 central exposure estimates for all eight direct factors.**
   GDD-IA and NHANES do not enter the direct-exposure path.
2. **Use GBD's processed-meat exposure directly.** Red meat is unprocessed red
   meat; processed meat is a disjoint factor.
3. **Drop NHANES from this workflow.** It cannot affect a GBD-anchored direct
   factor. It is also inappropriate as the calorie anchor because the GDD-IA
   energy estimate is explicitly normalized to anthropometric energy needs.
4. **Keep GDD-IA only for total calories, using adults aged 25+.** This matches
   the adult population for which GBD dietary risks are modelled. The input is
   fetched anonymously from the immutable Zenodo record.
5. **Merge the food and omega-3 baselines into
   `baseline_exposure.csv`.** Sodium remains in the implemented
   `baseline_mediators.csv`; it is intentionally not one of the eight direct
   rows per country.
6. **Preserve the current 175 countries.** Country expansion is a separate
   change because it requires new calorie proxies and complete burden inputs.
7. **Make the country universe explicit.** A checked-in manifest, not a
   generated CSV or sibling repository, is the source of truth.
8. **Keep one country-level adult mean per direct factor for this change.**
   This preserves the implemented direct-exposure estimand: the same direct
   risk ratio is applied within each age-sex burden stratum, while sodium has
   stratum-specific exposure and risk ratios. Country-mean direct exposure is a
   mean-field approximation, not a claim that averaging exposure before a
   nonlinear RR evaluation is exact. Moving direct factors to stratum-resolved
   exposure is separate future methodology work.
9. **Do not bundle exposure uncertainty yet.** The runtime does not propagate
   it. The builder validates `lower <= mean <= upper`, but only the weighted
   mean is emitted. Adding columns that the engine ignores would give a false
   impression of uncertainty support.
10. **Do not redesign sodium.** Preserve its mediator schema, curves, central
    mean-shift approximation, uncertainty caveats, supported causes and public
    result semantics. This change only replaces its country-list dependency and
    changes `f` through the reviewed adult calorie anchor.

## 4. Direct-exposure source and basis contract

The source is the official
[GBD 2023 Risk Exposure Estimates 1990-2023](https://ghdx.healthdata.org/record/ihme-data/gbd-2023-risk-exposure-estimates-1990-2023)
release. The files are authenticated, development-only inputs under
`data/raw/`; they are not redistributed in the package.

All files have the schema already enforced by
`build_baseline_nutrients_from_gbd.py`: `measure_id=19`,
`measure="continuous"`, male and female rows, 1990-2023, the 15 adult
five-year age groups, and finite ordered `mean/lower/upper` values. National
locations are selected by `location_id`, not by name, because the archives
also contain subnational locations such as the US state of Georgia.

| Factor | GBD file token | Archive | Internal and caller basis | Native-to-internal factor |
|---|---|---:|---|---:|
| `fruits` | `LOW_IN_FRUITS` | 1 | fresh/as eaten | 1.0 |
| `vegetables` | `LOW_IN_VEGETABLES` | 2 | fresh/as eaten | 1.0 |
| `whole_grains` | `LOW_IN_WHOLE_GRAINS` | 2 | current project dry-grain convention | 1.0 |
| `legumes` | `LOW_IN_LEGUMES` | 2 | dry/uncooked | 0.40 |
| `nuts_seeds` | `LOW_IN_NUTS_AND_SEEDS` | 2 | as eaten | 1.0 |
| `red_meat` | `HIGH_IN_RED_MEAT` | 1 | raw retail equivalent | 1.43 |
| `processed_meat` | `HIGH_IN_PROCESSED_MEAT` | 1 | preserved product as eaten | **1.0** |
| `omega3` | `LOW_IN_SEAFOOD_OMEGA_3_FATTY_ACIDS` | 2 | g/day EPA+DHA | 1.0 |

The 0.40 and 1.43 factors are modelling conversions, not properties of the
GBD files. They must live in one shared build-time registry used by both the RR
builder and the baseline builder. Missing entries mean 1.0. Processed meat is
deliberately removed from the 1.43 conversion and its public documentation is
changed to "product weight as eaten."

For unprocessed red meat, the same conversion must apply to **every quantity
on the dose axis**. If an RR estimate is reported per 100 g/day of consumed
meat, its dose unit becomes 143 g/day on the raw-retail internal axis, just as
the exposure knots and baseline do. The implementation must add an explicit
`source_basis` to `red_meat_rr_log_linear.csv` and test this conversion; merely
reusing the current `_override_all_ages()` behavior is not acceptable.

The current release files were verified locally with these SHA-256 digests:

| Factor | SHA-256 |
|---|---|
| `fruits` | `1bb089898d83ead3d5bd2843663bae3253fa31566aaf020cfdaab1333d99459a` |
| `vegetables` | `eb77c6d4bf4528d628116b8ca97faa0ff27483243885e27cfc3715e2fac2d562` |
| `whole_grains` | `ec0dd001d4fd7d808209fe1a2baa4a1e11211b51f4d0b55985440f4353dfb0c9` |
| `legumes` | `c968ee4d61b12500d0670e75d5e3d31b40666c74e56414bd25ff9688d5307fbb` |
| `nuts_seeds` | `a426371525fcfbbc5c356ab59b1c7f42a4d7cb270fd7278e195b6809f60e1de7` |
| `red_meat` | `e49458b2e4671b1ecd9633d27bd3712527f3e1c5d9a3babde57f101c17f5f871` |
| `processed_meat` | `c26f184c93d79395e7be0853013836c7d1e0949dab0d0b8f38209c6b2190845a` |
| `omega3` | `4e80f1047b13251d674da636d6cce35cb56b64878e79774c59f927d569d9b28f` |

### Aggregation

For each source country and factor:

1. select year 2020 and the 15 GBD adult age groups (25-29 through 95+);
2. join each age-sex cell to WPP 2020 male/female population;
3. fold WPP 95-99 and 100+ into GBD 95+;
4. calculate `sum(mean * population) / sum(population)`; and
5. apply the factor in the table above.

GBD covers every target national location except French Guiana in the
project's national-location set. `GUF` therefore uses `FRA`, as it already does
for omega-3. There are no other direct-exposure proxies.

## 5. Calorie source and adult weighting

Use `intake_kcals_2020.csv` from the public
[GDD-IA Zenodo record](https://doi.org/10.5281/zenodo.20818140), licensed
CC-BY-4.0. The builder downloads only this 82.9 MB file, not the parallel grams
file. It filters to:

```text
type=prim, food_group=all-fg, sex=BTH, residence=all-u, stats=mean
```

The current `baseline_calories.csv` is the `age=all-a` value. That choice mixes
children into the energy denominator even though GBD dietary risks and the
baseline exposures are adult 25+ quantities. The replacement uses the
`20-39`, `40-64` and `65+` GDD-IA rows, weighted by WPP 2020 population aged
25+.

The `20-39` value is applied to ages 25-39 because GDD-IA has no 25-year
boundary. This assumes per-capita energy is flat within 20-39. The assumption
must be stated in `docs/methodology.md` and tested by comparing a 20+ and 25+
anchor; it must not be hidden in code.

The exploratory calculation found that the current all-ages anchor is 10.9%
below the 25+ anchor on average across the 171 GDD-IA source countries, with a
larger gap in younger populations. This result should be regenerated by the
new builder and recorded as a test/report artifact rather than copied as a
permanent constant.

GDD-IA has 171 source countries. Twelve of the 175 target countries use the
existing curated calorie proxies:

```text
AFG->IRN  ASM->WSM  BRN->MYS  BTN->NPL  ERI->ETH  GNQ->CMR
GUF->FRA  PRI->USA  PSE->JOR  SOM->ETH  SSD->SDN  TWN->CHN
```

For a proxy target, use the source country's per-capita age-band values but the
target country's own WPP age weights. The assertion is similarity in diet, not
similarity in demographic structure.

The downloader pins Zenodo record `20818140`, verifies the record's published
MD5 (`6cad0a0ef06f3db5629af6619ddf9432`), and records a SHA-256 in the source
registry when the implementation is added. Network access is needed only to
regenerate the bundled CSV, never at package runtime.

## 6. Country manifest and output schemas

Add `tools/reference/baseline_country_sources.csv` with exactly 175 rows:

```text
country,gbd_exposure_source_country,calorie_source_country
AFG,AFG,IRN
GUF,FRA,FRA
USA,USA,USA
```

This single table defines the supported country set and the two independent
baseline proxy mappings. `gbd_exposure_source_country` is shared by the direct
dietary-exposure and sodium/SBP mediator builders; currently its only proxy is
`GUF->FRA`. It is reviewed data, not generated from an intersection that could
silently change when an upstream file changes. All three baseline builders and
`prepare_data.py` validate complete coverage against it. WHO mortality keeps
its own source-proxy mapping because its provider coverage differs, but takes
the target country set from this manifest.

`baseline_exposure.csv` replaces `baseline_intake.csv` and
`baseline_nutrients.csv`:

```text
country,risk_factor,exposure_g_per_day,source_country,source_year
GUF,fruits,<value>,FRA,2020
USA,omega3,<value>,USA,2020
```

Requirements:

- exactly one row for every manifest country x eight direct factors;
- finite, non-negative exposure;
- `source_year == 2020`;
- `source_country == gbd_exposure_source_country` in the manifest; and
- deterministic ordering and byte-stable float formatting.

`baseline_calories.csv` becomes:

```text
country,kcal_per_day,source_country,source_year
AFG,<adult-25+ value>,IRN,2020
```

It has exactly one finite positive row per manifest country, with provenance
matching `calorie_source_country`.

The implemented `baseline_mediators.csv` remains:

```text
country,age,sex,sodium_urinary_g_per_day_mean,
sodium_urinary_g_per_day_lower,sodium_urinary_g_per_day_upper,
sbp_mmhg_mean,sbp_mmhg_lower,sbp_mmhg_upper,source_country,source_year
USA,25-29,male,<mean>,<lower>,<upper>,<mean>,<lower>,<upper>,USA,2020
```

It retains exactly one row for every manifest country x 15 adult ages x two
sexes. Its values and uncertainty semantics do not change; its builder and
loader validate `source_country` against `gbd_exposure_source_country` rather
than inferring countries from `baseline_intake.csv`.

## 7. Builder architecture

Use three new/shared components and migrate the existing mediator builder:

```text
tools/dietary_exposure_sources.py
    pinned filenames, checksums, units, basis metadata, shared validators

tools/build_baseline_exposure.py
    eight GBD files + WPP + country manifest -> baseline_exposure.csv

tools/build_baseline_calories.py
    GDD-IA kcal file + WPP + country manifest -> baseline_calories.csv

tools/build_baseline_mediators_from_gbd.py
    existing sodium + SBP stratum builder; country manifest replaces
    baseline_intake.csv as its target-country input
```

`tools/prepare_data.py` imports the shared basis registry when constructing RR
curves. It may re-export `RR_BASIS_FACTOR` for compatibility with existing
tests, but there must be only one definition.

The direct builder generalizes the current omega-3 builder. Common GBD source,
schema, national-location and country-manifest validation is shared with the
mediator builder where their contracts genuinely match; direct WPP aggregation
and the mediator's exact age-sex join remain separate operations. The calorie
builder owns download/caching of the public Zenodo input. None of the builders
imports or shells out to GLADE.

After both builders exist, delete `tools/baseline_diet_from_glade.py` and the
now-redundant `build_baseline_nutrients_from_gbd.py`.

## 8. Loader and engine changes

`data.py` replaces `baseline_intake()` and `baseline_nutrients()` with one
strict cached `baseline_exposure()` loader. `available_countries()` reads its
validated country set; every other bundled loader validates coverage against
that same set. The checked-in manifest is the build-time authority, while
`baseline_exposure.csv` is its installed runtime representation.

`CountryBurden` loads all eight baselines from that table. An assessment still
activates omega-3 only when `seafood_omega3_mg` is not `None`; loading an
inactive baseline does not activate the factor.

`baseline_mediators()` remains a separate strict loader. `SodiumMeanShiftModel`
continues to load it only when `sodium_mg` is supplied. The public registry
continues to distinguish `DIRECT_NUTRIENT_FACTORS` (`omega3`) from
`MEDIATOR_FACTORS` (`sodium`); direct-baseline completeness tests must use the
former, not all of `NUTRIENT_FACTORS`.

Remove the silent `baseline.get(r, 0.0)` fallback for an active factor, or make
it unreachable with an explicit assertion. A missing baseline is corrupted
bundled data and must raise, not become a plausible zero exposure.

The substitution formula and public API otherwise remain unchanged:

```text
f = max(0, (C_base - C_meal) / C_base)
x_r = f * x_base,r + x_meal,r
```

This work does not alter cause mappings, mortality, life tables, age
attenuation, sodium curves, result objects or aggregation modes. In particular,
the implemented exact country-age-sex burden sum and sodium mean-shift path
remain intact.

## 9. Expected numerical changes

The following comparison was reproduced from the current bundled baseline and
GLADE's independently processed GBD exposure table, with `GUF->FRA`. It is a
cross-check of the intended direct-food shift, not a golden output for the new
builder:

| Factor | Current mean | GBD mean in current model basis | Shift (g/day) |
|---|---:|---:|---:|
| `fruits` | 115.5 | 117.9 | +2.4 |
| `vegetables` | 172.0 | 116.1 | -55.8 |
| `whole_grains` | 48.7 | 44.1 | -4.6 |
| `legumes` | 21.3 | 5.9 | -15.3 |
| `nuts_seeds` | 10.2 | 4.1 | -6.1 |
| `red_meat` | 50.8 | 41.3 | -9.5 |

Processed meat is omitted from this comparison because its input basis changes
from the unsupported raw-retail conversion to GBD-native product weight.
Omega-3 should remain byte-identical to the current
`baseline_nutrients.csv`; that is the strongest regression anchor for the
generalized builder.

The mediator baseline itself does not change. The calorie change is not
independent of sodium at runtime, however: raising `C_base` raises the shared
substitution factor `f`, so a fixed meal displaces slightly less direct diet
and slightly less baseline urinary sodium. Assessment outputs will therefore
change for two intended reasons: new direct baseline exposures and an adult
calorie denominator that also changes sodium substitution. Reference-value
tests must record those causes rather than merely accepting new numbers.

## 10. Tests and acceptance criteria

### Source and builder tests

- Schema, checksum, year, measure, sex and age validation for every pinned GBD
  file.
- National-location filtering by `location_id`, including a fixture with a
  colliding subnational name.
- Hand-calculated age-sex WPP weighting, including 95-99 plus 100+ folded into
  GBD 95+.
- Manifest coverage, direct, mediator and calorie proxy provenance, duplicate
  rejection, and deterministic byte-identical output.
- Omega-3 output byte-identical to the existing bundled table.
- One basis test per factor, including `processed_meat == 1.0` and the
  red-meat literature dose-unit conversion.
- GDD-IA stratum selection and a hand-calculated 25+ calorie aggregate.
- A proxy-calorie test proving that source age-band values use target age
  weights.
- Reconstruct GDD-IA `all-a` from its broad age bands within a documented
  tolerance as a live diagnostic of the weighting contract.

### Bundled-data and runtime tests

- Exactly `175 * 8 = 1400` direct-exposure rows, 5,250 unchanged mediator rows,
  and 175 calorie rows.
- Missing, extra, duplicate, non-finite or negative rows fail at load time.
- Omitted omega-3 remains absent; explicit `0.0` remains active and displaces
  the baseline.
- Preserve the implemented sodium tests for omission, explicit zero,
  monotonicity, stratum behavior, uncertainty-bound semantics, and additive
  attribution. Test explicitly that the new adult calorie anchor changes
  sodium only through the shared substitution factor, not by changing mediator
  baseline values.
- Existing hand-calculation tests continue to validate the formula.
- US sanity values are deliberately re-baselined and their change is explained
  in the test comment or changelog.
- `list_countries()` remains exactly the current 175-country set.

Acceptance requires the standard repository checks:

```bash
uv run pytest -q
uv run ruff format .
uv run ruff check .
uv run reuse lint
uv run --group docs sphinx-build -b html docs docs/_build/html
```

## 11. Documentation and provenance

Update together with the implementation:

- `docs/data_sources.md`: eight GBD files and checksums, GDD-IA calorie
  download, proxy manifest, source uncertainty, and the removal of operational
  GLADE dependence;
- `docs/methodology.md`: adult-25+ calorie anchor, the flat-within-20-39
  assumption, country-mean exposure approximation, and the statement that this
  is not an exact reconstruction of GBD PAFs, while retaining the implemented
  sodium mean-shift and exact burden-stratum sections;
- `docs/food_groups.md` and `foodgroups.py`: processed meat as product weight
  as eaten, plus a migration note for the former raw-retail wording;
- `src/mealhealth/data/DATA_PROVENANCE.md`: exact builders, source files,
  checksums, reference year and proxy rules; and
- `AGENTS.md`: the two new regeneration commands with no GLADE caveat.

Credit GLADE once as methodological provenance, including its role in the
anchoring and proxy choices. Do not claim that the new artifacts were generated
by GLADE.

## 12. Implementation order

1. Add the reviewed country/source manifest and the shared source/basis
   registry. Stage the seven additional GBD files and verify all eight hashes.
2. Correct the meat-axis contract: processed meat factor 1.0 and as-eaten
   public basis; explicit source/dose basis for each red-meat literature row;
   convert dose units together with exposure knots.
3. Generalize the omega-3 builder into `build_baseline_exposure.py`, generate
   the 1,400-row table, and prove omega-3 parity.
4. Add `build_baseline_calories.py`; first reproduce current non-proxy
   `all-a` values, then switch to the reviewed 25+ weighting and record the
   intended shift.
5. Migrate `build_baseline_mediators_from_gbd.py` and `prepare_data.py` from
   `baseline_intake.csv` to the manifest. Regenerate the mediator table and
   require a byte-identical result.
6. Migrate loaders and `CountryBurden`, remove silent missing-baseline
   fallbacks, and re-baseline assessment tests, including sodium assessments
   whose shared `f` changes with the calorie anchor.
7. Delete the two superseded direct-baseline builders and update all
   documentation and provenance.
8. Run the full validation suite above and inspect the generated CSV diff and
   several direct-only and sodium-enabled country assessments before
   committing.

No redesign of the sodium mediator, sex-resolved mortality, supported causes or
exact-stratum burden engine belongs in this implementation. They are existing
behavior to preserve.
