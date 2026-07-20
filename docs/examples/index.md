<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Examples

Worked examples, executed against the bundled data every time this site is
built. The figures you see were produced by the code shown above them; nothing
is stored or hand-drawn.

Each page is a notebook. Use the download button at the top right to get it as
`.ipynb` and run it yourself.

- [A first assessment](first_assessment.md) — one meal, read line by line: the
  headline number, the per-cause split, and why a meal is credited for foods it
  does not contain.
- [Comparing meals](comparing_meals.md) — five meals side by side, which is
  what the model is actually good for.
- [The same meal across countries](across_countries.md) — one burger in 175
  countries, and why the answer moves by a factor of three.
- [Dose and response](dose_response.md) — sweeping one food group from nothing
  to a lot, where the curve's nonlinearity and its plateau become visible.
- [Age](age_gradient.md) — how the lifetime effect changes with the age of the
  person eating.
- [Sodium](sodium.md) — the mediated pathway, and what its approximation costs.
- [Under the hood](under_the_hood.md) — plotting the relative-risk curves and
  baseline exposures directly, for anyone who wants to check the model rather
  than use it.

```{toctree}
:hidden:

first_assessment
comparing_meals
across_countries
dose_response
age_gradient
sodium
under_the_hood
```
