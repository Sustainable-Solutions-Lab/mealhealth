<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Design: sodium as a risk factor in `mealhealth`

Status: reviewed design. The scientific architecture, first-release mean-shift
estimand, production sodium-to-SBP response, TMREL treatment, uncertainty
execution model, and public result semantics are decided. Sodium is **not ready
for implementation** until the external data gates and the runtime performance
prototype in section 7 are complete.
Implementing sodium also moves `mealhealth` to a sex-resolved exact-stratum
engine, which intentionally shifts existing non-sodium results (section 5);
backward numerical compatibility with the pre-sodium engine is not a goal.
This document supersedes the sodium notes in `PLAN_omega3_sodium.md`.

The generic nutrient API already implemented for seafood omega-3 remains the
right public interface: elemental sodium is supplied in mg, omission (`None`)
means “do not assess sodium”, and an explicit `0.0` is a measured zero. Sodium
is not, however, an ordinary nutrient curve. Its cardiovascular and renal
effects require an explicit sodium -> systolic blood pressure (SBP) -> disease
mediator calculation.

## 1. Decisions after review

The following choices are requirements, not open options:

1. **Use an explicit mediator model in the engine.** Do not bundle
   country-invariant synthetic sodium-to-disease curves. Such curves are valid
   only under the older constant-slope/log-linear approximation and cannot
   represent current nonlinear SBP curves, country-specific baseline SBP, or
   sex-specific sodium exposure.
2. **Use current GBD 2023 Burden-of-Proof (BoP) curves where they exist.** The
   public BoP manifest currently exposes `High systolic blood pressure`
   (`rei_id=107`) for IHD, stroke, atrial fibrillation, aortic aneurysm,
   peripheral arterial disease, and CKD. It exposes `Diet high in sodium`
   (`rei_id=124`) directly only for stomach cancer (`cause_id=414`).
3. **Model country x age x sex strata and aggregate by cause-specific YLL, not
   population counts.** Men and women differ in sodium exposure, baseline SBP,
   cause-specific mortality, and remaining life expectancy. Population weights
   alone are not the correct weights for a YLL result. This is adopted as the
   engine-wide aggregation for *all* risk factors, not a sodium-only branch:
   `mealhealth` moves definitively to a sex-resolved exact-stratum engine (see
   section 5). Doing so shifts previously reported non-sodium results, because
   the sex split and the exact stratum sum replace the current single-anchor
   effective-curve approximation. That drift is accepted; bit-for-bit backward
   compatibility with pre-sodium numbers is explicitly **not** a goal. The only
   invariant preserved is that omitting a factor (including `sodium_mg=None`)
   excludes it from the assessment entirely.
4. **Treat dietary sodium and urinary sodium as different quantities.** The API
   accepts dietary elemental sodium; GBD sodium exposure is average 24-hour
   urinary sodium excretion. The conversion belongs in the sodium mediator,
   with uncertainty, not as a silent registry constant.
5. **Use an identifiable published RCT estimate for sodium-to-SBP.** The
   production model uses Filippini et al.'s directly reported linear estimate,
   not an irreproducible refit of an unpublished extraction dataset. Published
   effect-modifier models are mandatory transport sensitivities.
6. **Propagate uncertainty in the calculation, rather than merely storing
   `rr_low` and `rr_high`.** The current engine reads only `rr_mean`; writing
   additional interval columns would not produce uncertainty in the result.
7. **Include outcomes according to prespecified evidence and data criteria, not
   implementation convenience.** Section 6 defines the release set.
8. **Every borrowed numeric constant must be re-derived from its cited source
   during implementation.** All effect sizes, confidence intervals, curve
   ranges, star ratings, TMREL endpoints, unit conversions, and recovery
   fractions quoted in this document are provisional transcriptions, to be
   double-checked against the primary source when the coefficient and curve
   artifacts are built. A successful, checksummed derivation from source is a
   hard implementation-success criterion (sections 7 and 10); a value that
   cannot be reproduced from its cited source blocks release of the outcome that
   depends on it.
9. **Use a stratum-mean sodium shift in the first release.** The sodium-to-SBP
   response maps the change in country x age x sex **mean** urinary sodium to a
   change in mean SBP, and the whole usual-SBP distribution is translated by
   that amount. The direct stomach-cancer path likewise evaluates its curve at
   the stratum mean. This is a deliberate mean-field approximation, not an
   individual exposure model and not an exact reconstruction of GBD's
   within-stratum sodium PAF calculation. Section 5 states the approximation and
   the future distributional extension explicitly.
10. **Keep coherent draws until after the requested result is aggregated.** Do
   not reduce every stratum to marginal lower/upper quantiles and then combine
   them. The first implementation bundles compact draw-level primitive inputs
   and performs vectorised interpolation and quadrature for the requested
   country at runtime. A performance prototype is a data gate; precomputed
   response tables may replace this later only if they preserve draw identity
   and pass exact parity tests.

These decisions make sodium a modest extension to the public API but a material
extension to the internal model and data schemas.

## 2. Estimand and interpretation

The intervention remains the package's existing one:

> If the relevant population in country `c` ate this meal every day in place of
> an isocaloric share of its baseline diet, how would expected YLL change?

For sodium, “the relevant population” is resolved internally into country,
five-year age, and sex strata. The meal supplies the same dietary sodium amount
to each stratum, while baseline mean urinary sodium and the usual-SBP
distribution differ by stratum. In the first release, each stratum is
represented by its mean urinary sodium: the intervention changes that mean and
translates the stratum's SBP distribution without changing its shape. It does
not model person-to-person sodium exposure or its correlation with SBP.

`mode="age"` remains an expected person of the requested age in that country,
averaged over the country's male/female population and population SBP
distribution. It is **not** a prediction for a named individual and must not be
described as one. Personal SBP, hypertension treatment, kidney function, and
salt sensitivity remain outside the API.

The result is a chronic steady-state effect of eating the meal daily. It is not
an acute BP response to one meal.

## 3. Evidence model

### 3.1 Direct path: sodium -> stomach cancer

Use the current GBD 2023 BoP curve for `rei_id=124`, `cause_id=414`. The live
metadata check on 2026-07-14 found a 3-star curve, in g/day, covering roughly
1.14-7.36 g/day. This supersedes the GBD 2019 workbook curve currently discussed
in the old notes.

The curve is age-aggregated and GBD 2019 reports no age or sex modification for
this pair. Replicate it across adult ages and sexes rather than inventing an age
shape. Stomach-cancer mortality must be added to the burden data.

The direct curve uses the urinary-sodium exposure axis. It must receive the
same converted exposure as the mediated path. Because stomach cancer is disjoint
from every SBP-mediated cardiovascular and renal cause, the direct and mediated
paths never touch the same cause, so combining them introduces no double
counting.

Note one range mismatch to handle explicitly: the live curve starts near
1.14 g/day while the sodium TMREL floor (section 4) is 1 g/day, so a TMREL draw
`t` in `[1, 1.14)` yields effective exposures below the curve's first knot, where
`log_rr` clamps to that knot. This is harmless for the ratio
`RR(u1_eff)/RR(u0_eff)` but must be covered by a test rather than discovered
later.

### 3.2 Mediated path: sodium -> SBP -> disease

GBD treats sodium's cardiovascular and renal effects as mediated by SBP. The
GBD 2021 dietary methods list a mediation factor of exactly 1 for all retained
sodium -> SBP -> outcome paths. No additional mediation discount is therefore
applied. This is also appropriate because `mealhealth` does not expose SBP as a
separate user-supplied risk factor.

The old design's proposed equation,

```text
log RR_sodium,d,a(x) = log(RR_SBP,d,a per 10 mmHg) / 10 * beta_a * x,
```

is useful as a regression test only. It assumes both legs are log-linear and
hard-codes an age-only sodium slope. The production calculation instead keeps
the nonlinear SBP curve and explicitly reports the remaining sodium-response
transport uncertainty.

### 3.3 Sodium -> SBP response

The response function must estimate the chronic change in mean SBP caused by a
change in stratum-mean habitual urinary sodium after applying the sodium-risk
TMREL convention in section 4:

```text
delta_sbp = H(u_new_eff, z) - H(u_base_eff, z)
```

where `z` denotes effect modifiers used only by prespecified sensitivity
models. `H` is a response of **mean SBP to mean achieved urinary sodium**, not
an individual-level structural equation. The primary response is linear:

```text
H(u) = beta * u
beta = 2.42 mm Hg per (g/day urinary sodium)   [canonical internal unit]
```

**Unit convention.** All sodium-to-SBP slopes in this design are expressed in
the single canonical internal unit **mm Hg per g/day urinary sodium**. Several
sources publish their slopes per 100 mmol/day of sodium instead; convert with
`100 mmol/day sodium = 2.299 g/day` (100 mmol x 22.99 mg/mmol). Each slope below
is given in the canonical unit with the published native value in parentheses so
the conversion is auditable. The pinned coefficient artifact (section 7) stores
only the canonical-unit values and records each native value and its conversion
alongside; nothing downstream re-derives units.

Filippini et al. (2021) obtained the primary estimate from 85 randomized trials
with 24-hour urinary sodium, at least four weeks of follow-up, and achieved
exposures from 0.4 to 7.6 g/day. The reported 95% CI is 1.97-2.87 mm Hg per
g/day. Their flexible model was approximately linear, so using their reported
linear estimate avoids unsupported curve reconstruction while retaining the
main result. For parameter-uncertainty draws use a positive-truncated normal
with mean 2.42 and standard error `(2.87 - 1.97) / (2 * 1.96)`. Record that this
captures uncertainty in the pooled slope, not the full between-study or
transport uncertainty.

The pooled evidence is not population-standardized: 65 trials enrolled people
with hypertension, 11 people without hypertension, and nine mixed populations.
Consequently, all releases must show these named transport sensitivities, each
already converted to the canonical unit:

- Filippini's reported subgroup slopes: 1.00 mm Hg per g/day in trials without
  hypertension (2.30 per 100 mmol/day) and 2.83 mm Hg per g/day in trials with
  hypertension (6.50 per 100 mmol/day), with their published confidence
  intervals. These are scenario bounds, not individual treatment rules. The
  primary 2.42 slope correctly sits between them, near the hypertensive end, as
  expected from the 65/85 hypertensive-trial mix.
- Huang et al.'s multivariable estimate of 0.96 mm Hg per g/day across all
  eligible trials (2.20 per 100 mmol/day), and 1.87 mm Hg per g/day for trials
  lasting more than 14 days (4.30 per 100 mmol/day). The separately reported
  4.26 mm Hg is the pooled SBP change in the longer-duration trial group, not a
  per-100-mmol regression slope. Its published age,
  ethnicity, and baseline-SBP associations are evidence of transport
  uncertainty, not coefficients to splice into the Filippini model.
- The exact Mozaffarian et al. (2014) GBD-lineage equation, stated in its native
  per-100-mmol/day form and converted as a whole. For a 100 mmol/day reduction
  the magnitude is
  `3.735 + 0.105 * (age - 50) + 1.874 * hypertensive + 2.489 * Black` mm Hg;
  dividing by 2.299 gives the canonical per-(g/day) form
  `1.624 + 0.0457 * (age - 50) + 0.815 * hypertensive + 1.082 * Black` mm Hg per
  g/day. Report the non-Black normotensive age curve, the hypertensive
  increment, and the Black increment separately. Do **not** infer either race
  or hypertension from country membership.

Every numeric slope, CI, and conversion in this subsection is provisional until
re-derived from the cited article during implementation (decision 8); the
coefficient artifact's build must reproduce them from source.

The evidence audit found no public arm-level extraction table or fitted spline
coefficients in the Filippini article, Data Supplement, PMC archive, repository
record, or data repositories searched on 2026-07-14. Its supplement contains
search strategies, intervention descriptions, risk-of-bias assessments, and
sensitivity figures, not the observations needed to refit the one-stage model.
Huang likewise reports regression coefficients but not everything needed to
reconstruct individualized predictions (notably the intercept/reference
covariate vector and joint covariance in a portable model artifact). A claimed
refit from either supplement would therefore be irreproducible.

Create a versioned, human-readable reference artifact containing the primary
slope and uncertainty, every sensitivity coefficient, units, signs, source
table/page, evidence-population definition, and source-file hashes. If authors
later release the extraction data and a checked refit materially improves
transport, treat that as a separately reviewed model-version change rather
than silently replacing the published model.

### 3.4 SBP -> outcome response

Fetch and pin the nonlinear GBD 2023 BoP curves for `rei_id=107`. The live BoP
metadata check found these evidence ratings:

| BoP outcome | Cause ID | Stars | Publication-bias flag |
|---|---:|---:|---|
| Ischemic heart disease | 493 | 5 | yes |
| Stroke (all subtypes combined) | 494 | 5 | no flag |
| Atrial fibrillation and flutter | 500 | 2 | no flag |
| Aortic aneurysm | 501 | 3 | no flag |
| Lower-extremity peripheral arterial disease | 502 | 4 | no flag |
| Chronic kidney disease | 589 | 3 | yes |

The BoP curves are global and all-ages. Restore age structure using the same
documented donor approach already used by `mealhealth`: derive a multiplicative
log-RR age shape from the GBD 2019 per-age SBP table, normalized at 60-64, then
apply it to the current nonlinear all-age curve. This is a transparent vintage
bridge, not a claim that GBD publishes age-specific 2023 BoP curves. Validate
that the reconstructed per-10-mmHg age pattern matches the workbook.

The BoP stroke curve is an all-stroke curve. Apply the same sodium-mediated
stroke risk ratio to three **non-overlapping burden causes**: ischemic stroke,
intracerebral hemorrhage, and subarachnoid hemorrhage. Do not create a total
stroke burden alongside those subtypes, because that would count ischemic
stroke twice.

Reconcile this with the existing engine, which already carries a single cause
keyed `Stroke` and labelled *ischemic stroke* (populated today by the food-group
risks). That cause **is** the ischemic-stroke anchor above, not a separate total:
keep it (renaming to `ischemic_stroke` for clarity is preferred), confirm its
food-group BoP curves are ischemic-specific, and combine sodium's mediated
ischemic-stroke risk ratio with the food factors at that shared cause per the
section 5 product. Intracerebral haemorrhage and subarachnoid haemorrhage are
**new** causes with no food-group risks; each needs its own sex-specific
mortality anchor added to the burden data (section 7). Do not leave a legacy
both-sex `Stroke` total in `CAUSES` next to the subtypes.

Likewise, apply the CKD curve to the four GBD 2021 sodium-mediated CKD causes:
CKD due to type 2 diabetes, hypertension, glomerulonephritis, and other or
unspecified causes. Keep separate mortality anchors even if the RR curve is
shared.

## 4. Exposure conversion and intervention

Let:

- `m` be elemental sodium in the meal, in dietary g/day (`sodium_mg / 1000`);
- `f` be the existing isocaloric baseline scale;
- `u0[c,a,s]` be baseline stratum-mean 24-hour urinary sodium in g/day;
- `rho` be the fraction of ingested sodium recovered in 24-hour urine.

The intervention exposure is

```text
u1[c,a,s] = f * u0[c,a,s] + rho * m.
```

This formulation preserves GBD's urinary baseline and converts only the meal's
dietary sodium. It is algebraically equivalent to converting the baseline to a
dietary basis first if the same recovery fraction is used for the baseline, but
makes the measurement distinction explicit. It operates on stratum means; it
does not assert that every person has exposure `u0`.

Use `rho = 0.928` only as the central value. Lucko et al. (2018) estimated 92.8%
(95% CI 90.7-95.0%) and reported substantial heterogeneity. Draw `rho` in the
uncertainty calculation and include a wider scenario analysis. The caller must
include sodium from ingredients, sauces, cooking salt, and table salt; otherwise
the supplied meal value is incomplete.

Sodium means **elemental sodium**, not sodium chloride. Documentation should
give the optional conversion `salt_g * 1000 / 2.542` to mg sodium, but the API
must not guess which quantity the caller supplied.

### TMREL handling

GBD 2021 defines the sodium TMREL as a uniform distribution from 1 to 5 g/day
of urinary sodium. That interval is unusually wide and was based on literature
review and expert decision, not a sharply estimated biological threshold.

Do not collapse it silently to 3 g/day. For each uncertainty draw, draw
`t ~ Uniform(1, 5)` and use the harmful-risk effective exposure
`u_eff = max(u, t)` before evaluating either sodium path. In draw `j`, the
complete exposure and mean-SBP shift calculation is therefore:

```text
u1[j,c,a,s]     = f * u0[j,c,a,s] + rho[j] * m
u0_eff[j,c,a,s] = max(u0[j,c,a,s], t_sodium[j])
u1_eff[j,c,a,s] = max(u1[j,c,a,s], t_sodium[j])
delta_sbp[j,c,a,s]
                  = H[j](u1_eff[j,c,a,s]) - H[j](u0_eff[j,c,a,s])
                  = beta[j] * (u1_eff[j,c,a,s] - u0_eff[j,c,a,s])
```

Thus a sodium reduction below the draw's TMREL produces no additional modelled
SBP-mediated benefit, even though the underlying physiological response may not
have a true threshold there. This is the explicit GBD-style minimum-risk
convention used for the sodium risk calculation.

Report the central estimate as the mean across draws and the 2.5th and 97.5th
percentiles after aggregating each draw to the requested result. Also report
fixed-sodium-TMREL scenarios at 1, 3, and 5 g/day so readers can see how much the
result depends on this choice.

### SBP lower plateau

The public BoP SBP curves begin at approximately 115 mm Hg with RR 1 and clamp
below their first knot. Use that pinned lower plateau as part of the public
curve; do not add a second independently drawn SBP TMREL in the first release.
This is conditional on the public BoP representation and does not reproduce the
full GBD 2021 105--115 mm Hg SBP-TMREL uncertainty. Record that limitation and
include a fixed lower-plateau sensitivity if moving the plateau over 105--115
mm Hg can be implemented without unsupported curve extrapolation.

## 5. Calculation

For age `a` and draw `j`, let `RR_j,d,a(b)` be the age-expanded SBP BoP curve and
let `p_j,c,a,s(b)` be the distribution of usual SBP in the stratum. The
first-release mean-shift model translates this entire distribution by the
draw-specific change in mean SBP above. The mediated stratum risk ratio is

```text
q_sodium[j,c,a,s,d] =
    integral RR_j,d,a(b + delta_sbp[j,c,a,s]) p_j,c,a,s(b) db
    -------------------------------------------------------- .
                integral RR_j,d,a(b) p_j,c,a,s(b) db
```

Evaluate these one-dimensional integrals by tested Gaussian quadrature or a
fixed deterministic grid. Do not evaluate a nonlinear curve only at mean SBP;
`E[RR(B)]` is not generally `RR(E[B])`.

For stomach cancer, use the direct urinary-sodium curve at the stratum-mean
effective exposures:

```text
q_sodium[j,c,a,s,stomach] =
    RR_j,sodium(u1_eff[j,c,a,s]) / RR_j,sodium(u0_eff[j,c,a,s]).
```

This direct calculation is a mean-field approximation: in general,
`RR(E[U])` is not `E[RR(U)]`. It is retained for the first release to keep the
data and runtime model tractable and aligned with the existing package's use of
country-mean dietary exposures. External validation must quantify the resulting
bias rather than treating this as an exact reconstruction of the GBD sodium
PAF.

A future individual-exposure version should bundle a within-stratum urinary
sodium distribution and calculate the direct path as a ratio of expected RRs.
For the mediated path it may either retain the trial-supported mean-SBP response
or model `delta_sbp(U)` jointly over sodium and SBP; the latter requires a
defensible joint distribution or prespecified copula/correlation sensitivities.

Other food and nutrient risk factors retain their current age-specific risk
ratio `q_other[a,d]`. Within a cause and stratum:

```text
q_total[j,c,a,s,d] = q_other[a,d] * q_sodium[j,c,a,s,d]
delta_yll[j,c,a,s,d] = YLL[c,a,s,d] * (1 - q_total[j,c,a,s,d]).
```

Population mode aggregates each draw as:

```text
delta_yll_population[j,d] = sum_(a,s) delta_yll[j,c,a,s,d]
paf_population[j,d] = delta_yll_population[j,d] / sum_(a,s) YLL[c,a,s,d]
```

It must not first average log-RRs and then multiply one country-wide YLL anchor;
the latter is the current approximation and loses the sodium-specific sex and
SBP structure.

For individual lifetime modes, define the sex weight at the requested starting
age `a0` as

```text
pi[c,s,a0] = population[c,s,a0] / sum_s population[c,s,a0].
```

Then aggregate each draw using sex-specific survival, mortality, and remaining
life expectancy:

```text
delta_yll_individual[j,d] =
    sum_s pi[c,s,a0] * sum_(a >= a0) (
        S[c,s,a | a0] * m[c,s,d,a] * span[a] * ex[c,s,a]
        * (1 - q_total[j,c,a,s,d])
    ).
```

The median-person mode chooses `a0` from the combined-sex adult population and
then uses the same formula. This is a population-average result conditional on
being alive at `a0`, not a result for a person of unknown but fixed sex.

This exact aggregation over the modelled country x age x sex strata
**replaces** the current effective-curve
approximation for all factors, not only sodium: `mealhealth` adopts the
sex-resolved exact-stratum engine as its single aggregation path (decision 3).
“Exact-stratum” refers to burden aggregation; it does not remove the
within-stratum mean-shift approximation for sodium (decision 9).
Consequently previously reported non-sodium results shift, and that is accepted
— the goal is one principled aggregation, not numerical continuity with the
pre-sodium engine. The only preserved invariant is that an omitted factor
contributes nothing.

## 6. Outcome scope

The default release threshold is: current BoP rating >=3 stars for the direct
or SBP-to-outcome leg, a reproducible curve, a non-overlapping GBD mortality
cause, and complete country/age/sex burden data.

**Include in the first scientifically complete release:**

- stomach cancer (direct sodium curve, 3 stars);
- ischemic heart disease (SBP curve, 5 stars);
- ischemic stroke, intracerebral hemorrhage, and subarachnoid hemorrhage
  (shared all-stroke SBP curve, 5 stars; separate burden anchors);
- lower-extremity peripheral arterial disease (4 stars);
- aortic aneurysm (3 stars);
- CKD due to type 2 diabetes, hypertension, glomerulonephritis, and other or
  unspecified causes (shared CKD curve, 3 stars; separate burden anchors).

**Exclude from the default result, with the reason documented:**

- atrial fibrillation and flutter: current BoP rating is 2 stars; it may be an
  explicitly experimental sensitivity result;
- hypertensive heart disease: GBD assumes its high-SBP PAF is 1, but the current
  BoP service does not publish an exposure-response curve from which a marginal
  meal effect can be reconstructed;
- rheumatic heart disease, endocarditis, non-rheumatic valvular disease, and
  other cardiomyopathy: removed from the GBD 2021 high-SBP outcome set for lack
  of adequate evidence;
- CKD due to type 1 diabetes: removed from the GBD 2021 sodium-mediated set.

It is acceptable to implement and validate the included outcomes in stages,
but a reduced internal development stage must not be presented as the complete
sodium health effect.

## 7. Required data and schemas

### Already available

- GBD 2023 sodium exposure by country x age x sex, 1990-2023, in the staged
  `...DIET_HIGH_IN_SODIUM...CSV`; use 2020 to match mortality. The staged file
  provides marginal mean/lower/upper summaries, not source draw IDs or
  cross-stratum covariance.
- GBD 2019 per-age SBP RRs in
  `data/raw/IHME_GBD_2019_RELATIVE_RISKS_Y2020M10D15.XLSX` for the age-shape
  donor and regression comparison.
- Current public BoP metadata and curves for sodium -> stomach cancer and
  SBP -> the outcomes listed above.
- Sex-specific WPP population and life-table source files (the current processed
  files discard sex, so the builders and bundled schemas must change).

### Must be obtained or built before implementation

1. **GBD 2023 high-SBP exposure by country x age x sex**, preferably with
   source-backed joint draws; otherwise with central estimates, marginal
   uncertainty, and an explicitly reviewed correlation-scenario model.
   Download it from the authenticated risk-exposure release and pin it by
   filename and SHA-256.
2. **A defensible distribution of usual SBP in each stratum.** GBD 2021 models
   within-stratum SD and then applies age-specific usual-BP correction factors.
   The public mean exposure CSV alone is insufficient. The methods specify
   `log(SD)` as a function of `log(mean SBP)`, sex, and age indicators, but do
   not publish the fitted coefficients. They do publish the age-specific
   usual-BP correction factors (0.665 at 25-29 through 0.678 at 75+, with the
   full table in the high-SBP appendix). The appendix's displayed equation
   defines the factor as the square root of the between-person/observed
   variance ratio, implying `SD_usual = factor * SD_observed`; nearby prose and
   a figure caption are inconsistent with that equation. Resolve this against
   official code or output metadata and test it dimensionally rather than
   guessing. Preferred order: obtain GBD's modeled **usual-SD** output;
   otherwise obtain the official model code and coefficients. A defensible
   interim route is to refit the published GBD model form from public-use,
   nationally representative BP microdata, as specified below. Do not
   substitute an arbitrary global SD. Official GBD output remains the preferred
   replacement and validation target.
3. **Sex-specific GBD 2023 mortality rates** for every existing cause plus all
   included sodium causes. The currently staged mortality query contains only
   both-sex IHD, ischemic stroke, diabetes, and colorectal cancer, so it cannot
   support sodium.
4. **A pinned sodium-to-SBP coefficient artifact** implementing the published
   primary estimate and prespecified sensitivities in section 3.3. It stores
   every slope in the single canonical unit (mm Hg per g/day urinary sodium),
   records each source's native value and the conversion used, and its build
   must **re-derive every constant from the cited article** — a successful,
   checksummed source derivation is a hard success criterion (decision 8; the
   same requirement applies to the BoP curve ranges, star ratings, TMREL
   endpoints, and recovery fraction). No RCT microdata or new meta-regression is
   required for the first release.
5. **A GBD 2023 sodium-attributable validation extract** (PAFs or attributable
   deaths for selected countries, ages, sexes, and outcomes) from the Results
   tool. This is not a model input; it is an external validation target.
6. **A runtime and bundle-size prototype using synthetic draw-level inputs.** It
   must exercise one full country, all ages, both sexes, all included outcomes,
   fixed quadrature, and at least 500 coherent draws through the proposed NumPy
   runtime path. Record cold-call, warm-call, and peak-memory measurements on a
   documented reference machine. The initial acceptance targets are no more
   than 100 MiB of additional compressed bundled data, a cold sodium assessment
   below 500 ms, and a warm assessment below 100 ms. If those targets are not
   met, optimise or review the draw count and representation on Monte Carlo
   convergence evidence; do not fall back to marginal stratum quantiles.

Recommended bundled outputs:

- `baseline_mediators.csv`: `country,age,sex,sodium_urinary_mean,sbp_mean,sbp_sd`
  plus source/version fields;
- sex-specific `population.csv`, `life_table.csv`, and `mortality.csv` (or new
  versioned files with an explicit `sex` column);
- a transparent sodium-to-SBP JSON/CSV containing the published primary slope,
  sampling uncertainty, sensitivity-model coefficients, and provenance;
- pinned raw-cache files for the BoP curves and metadata;
- a compact draw artifact (for example compressed NPZ arrays behind a validated
  loader) containing aligned `draw_id`s for sodium/SBP baseline parameters,
  usual-SBP distribution parameters, sodium recovery, sodium TMREL, the primary
  slope, and coherent BoP curve representations. Global parameters are stored
  once, not repeated per stratum. The artifact records dtype, array shapes,
  seed, draw count, model version, source hashes, and a per-component provenance
  flag distinguishing source draws, parametric sampling approximations, and
  named correlation scenarios.

Do not aggregate sodium into the current one-row-per-country
`baseline_nutrients.csv`; that would discard exactly the strata the mediator
model needs. A country-wide mean may still be exposed as a display summary.

### Evidence audit of the remaining SBP gate

The following tempting substitutes were checked and rejected:

- NCD-RisC publicly provides country-, age-, and sex-specific **mean** SBP. It
  does not provide the marginal usual-SBP SD needed here. Its distribution
  paper models prevalence of raised BP, defined jointly as SBP >=140 or DBP
  >=90, against mean SBP and DBP. That joint prevalence does not identify the
  marginal SBP distribution, so solving a normal SD from it would add an
  unsupported assumption.
- WHO Global Health Observatory outputs similarly provide mean SBP or raised-BP
  prevalence, not the required within-stratum usual-SBP distribution.
- The public GBD 2016 code index identifies a “Standard deviation model” and
  “Usual blood pressure adjustment”, but the linked files currently require an
  authenticated GHDx session. The GBD 2021 high-SBP appendix confirms the model
  form and correction factors, not its fitted SD coefficients.
- The GBD 2021 appendix does publish more of the distribution-shape method than
  its text-only extraction initially suggests. It fits candidate two-parameter
  distributions by method of moments, chooses ensemble weights by minimising
  average Kolmogorov-Smirnov distance in person-level microdata, and estimates
  weights separately by sex before global averaging. Its SBP figure displays
  weights of 0.26 Gumbel, 0.23 inverse gamma, 0.19 lognormal, 0.18 log-logistic,
  and 0.14 gamma. Because that figure does not label the weights by sex, these
  displayed values are a reproducibility target rather than a substitute for
  the missing sex-specific output.

Accordingly, acceptable inputs are, in descending order:

1. country-age-sex GBD mean and usual-SD draws;
2. the official SD-model coefficients and distribution weights/code; or
3. a versioned open-data reconstruction that follows the published GBD model
   form and distribution-fitting algorithm.

For option 3, use nationally representative microdata with measured continuous
SBP: WHO STEPS for broad geographic coverage, supplemented by WHO SAGE and
NHANES for older ages (and DHS only where its age range and BP module are
suitable). Admission to the estimation panel requires respondent age and sex,
at least two SBP readings, an examination/measurement weight, and the available
survey-design variables (PSU and strata or replicate weights); record the
measurement protocol, fieldwork year, location, and antihypertensive-medication
variable where available. Harmonise the respondent-level SBP definition and
survey weights; compute design-weighted mean and cross-sectional SD in survey x
five-year-age x sex cells; fit `log(SD)` against `log(mean)`, sex, and age fixed
effects; and quantify sampling and between-survey uncertainty by a
survey-respecting bootstrap or hierarchical model. Refit the ensemble
distribution weights separately by sex using the published method-of-moments
and held-out KS criterion. Predict cross-sectional SD from the GBD 2023 mean,
then use the appendix equation's dimensionally consistent correction
`SD_usual = correction_factor * SD_cross_sectional`. Because the surrounding
appendix prose is inconsistent, also run the alternative interpretation
`SD_usual = sqrt(correction_factor) * SD_cross_sectional` as a named sensitivity
until official code resolves it.

This is not a fully automatic public-data pipeline. NHANES examination and
demographic XPT files are anonymously and directly downloadable. The WHO STEPS
catalog exposes machine-readable metadata, questionnaires, and dictionaries,
but currently labels its microdata files as licensed; WHO SAGE likewise uses a
registered microdata-request workflow (with an easier public-use SAGE mirror at
ICPSR, still requiring a one-time interactive acquisition). DHS respondent
microdata require project registration and survey approval, and BP is present
only in selected surveys. Therefore separate acquisition from deterministic
processing: maintain a versioned manifest containing survey identifier,
release, access date, licence, filename, and SHA-256 hash; have the build read
authorised raw files from an untracked local directory; and never bundle or
redistribute restricted respondent records. Review each survey's terms before
publishing derived cell statistics. An automatic-only NHANES reconstruction is
useful for implementation and validation, but is not an acceptable global fit
because it supplies only US population variation.

### Low-friction approximation route

If licensed WHO respondent data are out of scope, retain NHANES as the only
respondent-level input but do not claim that it identifies a global mean--SD
relationship. Pool protocol-compatible pre-pandemic NHANES cycles, use the
design weights and the mean of the second and third readings, and estimate a
smoothed age-by-sex reference distribution (including its empirical quantiles)
for ages 25+. Public NHANES ages top-code the oldest respondents, so estimate a
pooled 80+ anchor and make the 80+ extrapolation explicit.

For the otherwise unidentified dependence of SD on population mean, use the
public-domain WHO MONICA *Population Survey Data Book* as an aggregate-only
supplement: it reports SBP means, SDs, and quantiles from standardised random
population surveys in 38 populations in 21 countries, separately by sex, over
ages 35--64. It requires no respondent-data application, although its legacy
web archive must be snapshot and checksum-pinned. Fit only the mean elasticity
from those aggregate records, then transport the NHANES age-sex reference SD:

`SD_cross(c,a,s) = SD_NHANES(a,s) * (mean_GBD(c,a,s) / mean_NHANES(a,s))^gamma`.

Use a population/survey-clustered fit for `gamma`; retain its sampling
uncertainty and protocol/vintage sensitivity. The published sex-averaged GBD
ensemble weights may be used as a labelled approximation for distribution
shape, while NHANES empirical quantiles provide a diagnostic; do not represent
them as GBD's unpublished sex-specific weights. Apply the published usual-BP
correction after this step.

NHANES alone remains a permissible *fallback emulator*, not a reconstructed
GBD exposure model. In that case pre-specify a bounded mean-elasticity scenario
set (constant SD, estimated/constant-CV scaling, and the MONICA fit if later
available) rather than presenting a US-only coefficient as global evidence.
It may be released only if the full output is robust across those scenarios and
passes a direct, held-out comparison with GBD high-SBP PAFs. That diagnostic
uses `attributable deaths / total deaths for the same cause` for high SBP, by
country-age-sex-cause; it is the appropriate test of the constructed SBP
distribution. Keep it separate from the GBD sodium-PAF validation, and never
choose the primary scenario or tune its parameters using the held-out results.

Pre-specify leave-survey and leave-region-out validation, compare predicted
with held-out direct SDs and empirical SBP quantiles, and propagate coefficient,
correction-factor-interpretation, and distribution-family uncertainty through
the sodium result. Treat the MONICA-augmented route as an independently
reconstructed SBP distribution and the NHANES-only route as an emulator, not as
official GBD output; replace or benchmark either when IHME data arrive. Mean
SBP alone, a single literature SD, a coefficient of variation, or an SD
reverse-engineered from joint hypertension prevalence remains unacceptable.

## 8. Engine and API changes

1. Add `sodium_mg: float | None = None` to `assess_meal()` and `assess()` only
   after all required data exist. Validate finite, non-negative values.
2. Register sodium as a harmful, mediator-backed nutrient with public unit mg
   and internal **dietary** unit g/day. Keep `api_to_internal=0.001`; do not hide
   urinary recovery in that constant. Refactor the nutrient registry so it
   distinguishes `direct_curve` factors (currently omega-3) from `mediator`
   factors (sodium), while `nutrient_factors()` exposes both. Only direct-curve
   factors participate in the strict one-row-per-country
   `baseline_nutrients.csv` coverage check; sodium loads its stratum baseline
   from `baseline_mediators.csv`. Do not add a fake country-mean sodium row merely
   to satisfy the current loader.
3. Add a mediator abstraction rather than sodium conditionals scattered through
   `model.py`. A mediator returns stratum-specific risk ratios and uncertainty
   draws for its outcome set.
4. Extend country burden data to sex-specific strata and calculate YLL weights
   from cause-specific death rates, population, and sex-specific remaining life
   expectancy.
5. Keep direct nutrient/food curves on the existing path. Combine their risk
   ratios with mediator risk ratios only at the non-overlapping cause-stratum
   level.
6. Define the public exposure summaries explicitly. When sodium is active,
   `baseline_exposure["sodium"]` and `exposure["sodium"]` are adult-population-
   weighted **urinary-sodium means** in g/day before TMREL clipping; the dietary
   API input remains available as `meal_inputs["sodium_mg"]`. Structured
   diagnostics expose `u0`, `u1`, `u0_eff`, `u1_eff`, and `delta_sbp` by stratum
   with their units. When sodium is omitted, none of these sodium keys appear.
7. Add uncertainty-aware result fields at total and cause level: mean, lower,
   upper, draw count, seed, and model version. The existing scalar `paf` and
   `delta_yll` fields are aliases of the draw means. Add a scalar
   `risk_ratio = 1 - paf`. Deprecate `rr_baseline` and `rr_meal`: under exact
   stratum aggregation there is no unique pair of absolute aggregate RRs. During
   the compatibility period expose normalized indices (`rr_baseline = 1`,
   `rr_meal = risk_ratio`) and document the changed meaning.
8. **Bundle compact draw-level primitives and evaluate one country
   vectorially at runtime.** Data preparation performs source reconstruction,
   generates aligned coherent draws, constructs compact BoP spline/curve
   representations, and pins fixed quadrature nodes and weights. At runtime the
   API loads only the requested country's stratum arrays, computes draw vectors
   for `u1`, `u_eff`, and `delta_sbp`, evaluates all stratum/cause integrals in
   batched NumPy operations, and aggregates each draw before calculating means
   and quantiles. Python loops over draws are prohibited; a small loop over
   causes or distribution families is acceptable when profiling supports it.
   Cache immutable country inputs and any baseline denominators within the
   process.

   Do not tabulate `q_sodium` over country x age x sex x cause x draw x grid in
   the first release. Such a table is too large, and reducing it to marginal
   stratum quantiles would destroy the shared-draw dependence needed for a sum.
   Also do not key an uncertainty interval only by a central `delta_sbp` or
   `u1_eff`: meals with the same central shift but different `(f, m)` have
   different uncertainty because baseline exposure and urinary recovery enter
   differently. The performance prototype in section 7 determines whether the
   compact runtime approach meets the release budget.
9. Define public aggregation and attribution as follows:
   - population `paf` is the draw-wise YLL-weighted PAF in section 5;
   - age/median `paf` is the sex-population-weighted risk change in the current
     age band, while `delta_yll` remains the lifetime sum;
   - `relative_only=True` skips reporting absolute YLL but deliberately uses the
     same bundled burden weights and returns the same PAF as the full result. It
     is no longer advertised as a fallback that works without mortality or life
     tables;
   - central `risk_attribution` uses an exact Shapley decomposition of the
     **draw-mean** `delta_yll` function over the active factors, evaluated at the
     cause-stratum level and then summed. Each subset value is aggregated over
     coherent draws before its Shapley contrasts are formed, so the attributions
     sum to the reported mean despite nonlinearity. Limit subsets to factors
     affecting that cause and use the exact dynamic-programming formula for a
     product of factor risk ratios rather than enumerating all `2^n` subsets.
     Report attribution intervals only after a draw-wise Shapley implementation
     has been validated; otherwise label attribution as central-only.

The product of food/nutrient and sodium risk ratios is an explicit independent-
risk assumption, not a uniquely identified pathway decomposition. Processed
meat is the clearest concern because an observational processed-meat RR may
partly capture sodium-related mechanisms; some other dietary risks also have
SBP-mediated components in GBD's mediation matrix. The primary calculation
follows the package's existing multiplicative convention. Publish a sensitivity
with processed meat disabled, document the broader mediator overlap, and do not
describe sodium's Shapley attribution as a biologically unique decomposition.

## 9. Uncertainty

The sodium analysis must propagate coherent Monte Carlo draws, or explicitly
separated scenario sets where joint probability information is unavailable,
over at least:

- the primary sodium-to-SBP slope using its published sampling uncertainty;
- BoP RR uncertainty (coherent curve draws, not independently sampled knots);
- sodium and SBP baseline-estimate uncertainty;
- the usual-SBP distribution parameters;
- urinary recovery `rho`;
- the uniform 1-5 g/day sodium TMREL.

These draws are generated and aligned at build time, stored as compact primitive
arrays, and evaluated vectorially for the requested country at runtime (section
8, item 8). Draw identity is retained through exposure conversion, integration,
cause/stratum aggregation, and only then reduced to a mean and percentile
interval. The draw count and seed are recorded. Choose the production draw count
from a convergence study of total and major-cause means and interval endpoints;
500 draws is the minimum performance-prototype size, not an unquestioned final
constant.

If IHME does not expose coefficient/draw covariance for a BoP curve or joint
draws for a baseline exposure surface, distinguish clearly between:

- a formal interval based on quantities for which joint draws are available;
  and
- a scenario/sensitivity envelope for the BoP curve.

Do not label a pointwise-low/pointwise-high envelope a 95% uncertainty interval.
Likewise, marginal exposure bounds do not identify cross-age/sex/location
correlation. If source draws cannot be obtained, evaluate at least fully
rank-correlated and stratum-independent sampling constructions as named
correlation scenarios; do not mix either construction into the formal interval
without labeling the added assumption. A formal headline interval may therefore
be conditional on central baseline exposures, accompanied by a separate
baseline-uncertainty envelope.

Likewise, report the Filippini, Huang, and Mozaffarian transport results as
named sensitivity scenarios, not as draws from a fabricated probability
distribution. The primary slope's confidence interval is not a substitute for
between-study heterogeneity or model-transport uncertainty.

Mortality and life-table uncertainty may remain a documented second-order
omission initially if the headline interval is explicitly “exposure-response
uncertainty conditional on the burden inputs”.

Existing food and omega-3 factors currently use only their central RR curves.
Until their uncertainty machinery is upgraded too, a multi-factor meal's
interval is also conditional on those non-sodium curves; do not label it a full
uncertainty interval for the entire meal model.

The headline interval is also conditional on the fixed public BoP SBP lower
plateau and the stratum-mean sodium approximation. Neither is silently absorbed
into a nominal 95% interval; their effects are reported as named sensitivities.

## 10. Validation and release gates

All of the following are required:

### Unit and mathematical tests

- `sodium_mg=None` excludes sodium entirely: no sodium exposure key, no sodium
  cause contribution, identical to a build without the sodium factor. Bit-for-bit
  reproduction of *pre-refactor* numbers is **not** required — the move to the
  sex-resolved exact-stratum engine deliberately shifts existing non-sodium
  results (decision 3). Guard those instead against a documented post-refactor
  reference, and check the pre/post drift is explained by the sex split and
  stratum aggregation, not a regression (direction and rough magnitude sanity per
  cause).
- Explicit zero sodium is included and displaces baseline sodium.
- `u1 == u0` gives exactly zero sodium contribution.
- More sodium never improves a modelled outcome within the supported exposure
  range; TMREL capping behaves correctly in every draw.
- Dietary-to-urinary conversion is tested independently of substitution.
- The mediated `delta_sbp` uses TMREL-clipped `u0_eff` and `u1_eff` exactly as
  specified in section 4; test cases on both sides of and crossing the TMREL are
  required.
- Numerical SBP integration agrees with a dense-grid reference and with a hand
  calculation for a synthetic two-sex/two-age country.
- Cause anchors are disjoint; the three stroke and four CKD causes sum without a
  parent-cause duplicate.
- Draws are aggregated before quantiles: a synthetic correlated two-stratum
  example must reproduce a direct draw-wise hand calculation and must differ
  from the deliberately incorrect aggregation of marginal stratum quantiles.
- Two meals engineered to have the same central `delta_sbp` but different
  `(f, m)` must retain their appropriately different uncertainty from baseline
  exposure and `rho`.
- Population and individual sex aggregation reproduce explicit two-sex hand
  calculations, and `relative_only=True` returns the same PAF as the full result.
- The central Shapley attributions sum to total central `delta_yll` for every
  mode, including opposing protective and harmful factor changes.

### Source reconstruction tests

- Rebuild and checksum all reference artifacts deterministically.
- Reproduce published central sodium-to-SBP contrasts from the primary paper.
- Reproduce current BoP curve knots and metadata IDs.
- Reproduce the GBD 2019 per-age SBP age pattern used as the donor.
- Re-derive every borrowed constant (effect sizes and CIs, curve ranges, star
  ratings, TMREL endpoints, recovery fraction, unit conversions) from its cited
  source; a value that cannot be reproduced blocks its dependent outcome
  (decision 8). This is a hard gate, not a diagnostic.
- Confirm the compact runtime calculation matches an intentionally slow,
  independently implemented direct-quadrature and draw-loop reference within a
  pinned tolerance.
- Verify the draw artifact schema, `draw_id` alignment, dtype, shapes, seed,
  model version, and source hashes at load time.

### External validation

- Compare modelled 2020 sodium PAFs for IHD, stroke, CKD, and stomach cancer
  against GBD Results for a prespecified diverse set of countries.
- For stomach cancer, separately quantify the mean-field error against a
  distributional calculation using the best available GBD-style sodium
  distribution or prespecified plausible distribution shapes. Do the same for
  the mediated path if an individual-exposure sensitivity can be constructed.
  This is a diagnostic of decision 9, not a coefficient-tuning target.
- Compare the historical linear/log-linear compatibility implementation against
  the Mozaffarian 2014 published global and country patterns.
- Investigate and document deviations before setting tolerances. Do not tune
  coefficients to make the validation countries match.
- Publish sensitivity rankings for the sodium-to-SBP model, SBP distribution,
  TMREL, urinary recovery, and excluded 2-star atrial-fibrillation path.
- If the Filippini hypertension subgroups or the Huang/Mozaffarian transport
  scenarios materially change an outcome's sign, ranking, or order of magnitude,
  the public summary must say that the result is transport-model dominated; the
  pooled-slope interval alone must not visually imply that this uncertainty is
  resolved.

Release is blocked if the direction is wrong, if a major country/outcome PAF is
outside its external uncertainty range without an understood methodological
reason, if the result is dominated by an undocumented default, if any bundled
constant cannot be re-derived from its cited source (decision 8), if the runtime
and bundle-size prototype misses its accepted budget without a reviewed remedy,
or if the vectorised runtime calculation disagrees with the independent slow
reference beyond a pinned tolerance.

## 11. Implementation order

1. Build the synthetic compact-draw runtime prototype and record the accepted
   performance, memory, bundle-size, and Monte Carlo convergence budgets.
2. Acquire and pin the missing SBP exposure/distribution and sex-specific
   mortality inputs.
3. Build and peer-review the published sodium-to-SBP coefficient artifact and
   its transport-sensitivity implementation, re-deriving every constant from
   source (decision 8).
4. Add sex-specific burden schemas and switch all factors to exact stratum
   aggregation (no sodium API yet). This step alone re-baselines existing
   non-sodium results; record the post-refactor reference here (decision 3).
5. Add and validate the mean-shift SBP mediator using synthetic inputs.
6. Add direct mean-field stomach cancer and the evidence-qualified mediated
   outcome set.
7. Build the aligned compact draw artifact, then perform external GBD validation,
   the mean-field sensitivity checks, and vectorised-runtime-versus-slow-reference
   parity tests.
8. Expose `sodium_mg`, then update methodology, food-group, usage, data-source,
   provenance, and citation documentation in the same release.

## 12. References and auditable sources

- GBD 2023 Disease and Injury and Risk Factor Collaborators. *Burden of 375
  diseases and injuries, risk-attributable burden of 88 risk factors, and
  healthy life expectancy ... 1990-2023*. Lancet (2025).
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC12535840/>
- GBD 2021 Risk Factors Collaborators. *Global burden and strength of evidence
  for 88 risk factors ... 1990-2021*. Lancet (2024).
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC11120204/>
- GBD 2021 Risk Factors Collaborators. *Supplementary appendix 1*, dietary-risk
  and high-systolic-blood-pressure sections (exposure definition, sodium TMREL,
  mediation table, mean/SD model, and usual-BP correction factors). Available
  from the supplementary-material links on the open-access article:
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC11120204/>
- IHME Burden of Proof visualization and public API (live curve metadata).
  <https://vizhub.healthdata.org/burden-of-proof/>
- NCD Risk Factor Collaboration. *Contributions of mean and shape of blood
  pressure distribution to worldwide trends and variations in raised blood
  pressure*. Int J Epidemiol. 2018;47:872-883i.
  <https://doi.org/10.1093/ije/dyy016>
- WHO. *NCD Microdata Repository* (public-use STEPS survey microdata and
  survey-specific metadata).
  <https://extranet.who.int/ncdsmicrodata/index.php/home>
- WHO. *Study on global AGEing and adult health (SAGE): SAGE waves* (older-age
  BP microdata, instruments, and sampling weights).
  <https://www.who.int/data/data-collection-tools/study-on-global-ageing-and-adult-health/sage-waves>
- US Centers for Disease Control and Prevention. *National Health and Nutrition
  Examination Survey: questionnaires, datasets, and related documentation*.
  <https://wwwn.cdc.gov/nchs/nhanes/Default.aspx>
- Mozaffarian D, et al. *Global sodium consumption and death from cardiovascular
  causes*. N Engl J Med. 2014;371:624-634.
  <https://doi.org/10.1056/NEJMoa1304127>
- Huang L, et al. *Effect of dose and duration of reduction in dietary sodium on
  blood pressure levels: systematic review and meta-analysis of randomised
  trials*. BMJ. 2020;368:m315. <https://doi.org/10.1136/bmj.m315>
- Filippini T, et al. *Blood pressure effects of sodium reduction: dose-response
  meta-analysis of experimental studies*. Circulation. 2021;143:1542-1567.
  <https://doi.org/10.1161/CIRCULATIONAHA.120.050371>
- Lucko AM, et al. *Percentage of ingested sodium excreted in 24-hour urine
  collections: a systematic review and meta-analysis*. J Clin Hypertens.
  2018;20:1220-1229. <https://doi.org/10.1111/jch.13353>

Every downloaded source and fitted artifact must also be recorded in
`docs/data_sources.md` and `src/mealhealth/data/DATA_PROVENANCE.md` when sodium
is implemented.
