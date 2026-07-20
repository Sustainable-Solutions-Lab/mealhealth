<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Troubleshooting

## Errors

**`KeyError: No bundled data for country 'XXX'`**

The country is not among the 175 with complete bundled data. `list_countries()`
returns the full set. Coverage requires GBD exposure, WHO mortality, UN WPP
population and life tables, and a GDD-IA calorie row all to be present for the
same country, so small territories and a few states with sparse reporting fall
out. There is no partial-data mode; use a neighbouring country deliberately, and
say that you did.

**`ValueError: Unknown meal food groups: ['chocolate']`**

Only the seven keys in `mealhealth.RISK_FACTORS` are accepted in `meal`.
Everything else in the meal — poultry, fish, eggs, oils, refined grains,
potatoes, sugar, dairy — enters through `meal_kcal` alone. That is not a
limitation of the input format but of the model: GBD publishes no dose–response
curve for those foods, so their only modelled effect is displacing baseline
diet. Seafood omega-3 and sodium are supplied through their own keyword
arguments, not as food-group masses.

**`ValueError: include_processed_meat=False excludes processed meat …`**

You disabled the group and then supplied it. Pick one. Note that the flag drops
processed meat from the model entirely, the country's baseline intake included,
so it is not the same as passing `processed_meat: 0`.

**`ValueError: mode='age' requires the age argument (years)`** and
**`ValueError: age must be a finite number at least 25`**

The bundled risk curves start at the 25–29 age band, so there is no basis for
assessing a younger person. For a whole-population figure use the default
`mode="population"`; for a typical adult use `mode="median"`.

**`ValueError: seafood_omega3_mg must be a finite non-negative number`**
(likewise `sodium_mg`, `meal_kcal`)

Usually a `NaN` arriving from a nutrition database join. Note that `None` is
accepted and means "do not assess this factor", while `0.0` is a measured zero —
they give different answers, and the difference is explained in
[Food groups](food_groups.md#nutrient-inputs).

**`ValueError: per_meal_marginal is defined for individual lifetime modes`**

The per-meal figure divides a lifetime quantity by a lifetime's meals.
Population mode returns an annual population total, so the division would be
meaningless. Re-run with `mode="median"` or `mode="age"`.

## Warnings

**"Meal energy (… kcal) >= baseline daily energy (… kcal)"**

Your meal's calories meet or exceed the country's entire daily intake, so the
baseline scale `f` clamped to zero and the meal became the whole day's diet.
Sometimes that is what you meant. More often `meal_kcal` is wrong — check it
against `result.baseline_kcal`, which ranges from 2181 to 2840 across the
bundled countries.

**"Sodium uses a central stratum-mean approximation …"**

Expected whenever `sodium_mg` is supplied; nothing is wrong with your input. It
records that the sodium pathway carries no uncertainty interval and cannot be
read as an individual prediction. See
[Limitations](../model/limitations.md#sodium-is-a-mean-shift-approximation).

## Results that look wrong

**The numbers are in the millions.** You are in population mode, which reports
an annual whole-country total. Pass `mode="median"` for a per-person lifetime
figure. See [Interpreting results](interpreting.md#the-three-modes-are-three-different-quantities).

**A healthy meal is penalised on a group it does not contain.** Expected, and
worth understanding before you report anything: the meal displaces part of the
baseline diet, so it inherits a penalty for whatever protective foods that
displaced share contained. [Interpreting
results](interpreting.md#risk-attribution-has-a-trap-in-it) works through an
example.

**Whole grains or legumes look far too influential.** Check the mass basis.
Those two are **dry, uncooked** weight, so passing 150 g of cooked brown rice
where 67 g dry was meant inflates the exposure by more than double. The bases
are listed in [Food groups](food_groups.md#mass-basis-and-why-it-matters).

**Sodium effects are enormous.** Check you passed elemental sodium in mg and not
salt. A gram of salt is 393 mg sodium, so passing salt mass overstates sodium by
about 2.5×. Convert with `sodium_mg = salt_g * 1000 / 2.542`.

**Two countries differ more than expected.** Baseline diets, baseline calories
and disease burdens all differ, and the same meal legitimately produces very
different results — the same burger costs 0.71 years in France and 2.02 in
India. Before reporting an outlier, check `result.baseline_kcal` and
`result.baseline_exposure` for that country to see which input is driving it.

## Data-build problems

**`FileNotFoundError: Missing manually downloaded data …`**

Run `uv run python -m tools.build_data --list-inputs` for the authoritative list
of what is expected and what is missing, then
[Rebuilding the bundled data](../development/data_build.md) for where each file
comes from.

**HTTP 403 fetching the Burden-of-Proof curves.** The IHME JSON endpoints sit
behind Cloudflare's edge bot-check, which normal machines pass and cloud IP
ranges often do not. Run the build once from an ordinary machine; the curves are
cached at `data/raw/bop_rr_curves.csv` and reused afterwards.

**`SHA-256 mismatch` or `Checksum mismatch`.** An upstream file has been
republished, or a download was truncated. Delete the file and retry; if the
digest still differs, the upstream release genuinely changed and the pin needs a
reviewed update rather than a quiet edit.
