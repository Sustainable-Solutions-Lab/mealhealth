<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Design notes

Working notes on decisions that shaped the model, kept because the reasoning
behind them is not recoverable from the code. They are internal documents, not
user documentation: they record what was decided and why, including options
that were considered and rejected, and parts of them describe work that is
designed but not implemented.

Where a design note and the rest of this site disagree about current behaviour,
the rest of the site is right.

- [Baseline diet](baseline_diet.md) — how the per-country baseline exposure and
  calorie anchor are defined, and why the baseline is built directly from GBD
  exposure files rather than inherited from a sibling project.
- [Sodium](sodium.md) — the full sodium design, including the distributional
  treatment that the shipped mean-shift approximation deliberately falls short
  of. Read this before changing anything in `sodium.py`.

```{toctree}
:hidden:

baseline_diet
sodium
```
