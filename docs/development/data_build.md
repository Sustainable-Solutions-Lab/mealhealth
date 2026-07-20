<!--
SPDX-FileCopyrightText: 2026 Koen van Greevenbroek

SPDX-License-Identifier: CC-BY-4.0
-->

# Rebuilding the bundled data

The ten CSVs under `src/mealhealth/data/` are checked in, so **using**
mealhealth never requires this. You need it when an upstream release is
refreshed, when you want to verify the bundled numbers yourself, or when you
need a commercially licensed rebuild from your own copies of the IHME data.

The whole build is one command:

```bash
uv run python -m tools.build_data
```

It validates the manually staged inputs, downloads everything else, runs the
five stages in dependency order, and publishes to `src/mealhealth/data/` only
after every stage has succeeded. A failure part-way leaves the bundled data
untouched.

## What you have to stage yourself

Three IHME archives, requiring a free account. Everything else downloads.

Ask the tool what it wants and whether it has it:

```bash
uv run python -m tools.build_data --list-inputs
```

That prints all eleven expected files with their pinned SHA-256 digests and
whether each is present. It reads the same registry the build reads, so it
cannot drift out of date — prefer it to any list written down here.

### GBD 2023 Risk Exposure Estimates (eight files, two archives)

1. Sign in to a free IHME account and open the
   [GBD 2023 Risk Exposure Estimates 1990–2023 record](https://ghdx.healthdata.org/record/ihme-data/gbd-2023-risk-exposure-estimates-1990-2023).
2. Accept the IHME Free-of-Charge Non-commercial User Agreement and download
   `IHME_GBD_2023_RISK_EXPOSURE_DIET_1.zip`,
   `IHME_GBD_2023_RISK_EXPOSURE_DIET_2.zip`, and
   `IHME_GBD_2023_RISK_EXPOSURE_OTHER_1.zip`. Direct links redirect to a login
   page unless the browser session is authenticated, which is why the builder
   does not attempt the download itself.
3. Extract each archive under `data/raw/`, keeping the archive name as the
   directory name: `data/raw/IHME_GBD_2023_RISK_EXPOSURE_DIET_1/` and so on.

These supply the seven food-group exposures, seafood omega-3, urinary sodium,
and systolic blood pressure. Do not rename the CSVs inside — the pinned
digests are checked against the exact filenames.

### GBD 2023 theoretical minimum risk life table (one file)

Download **Theoretical minimum risk life table** from the
[GBD 2023 Demographics 1950–2023 record](https://ghdx.healthdata.org/record/ihme-data/gbd-2023-demographics-1950-2023)
(sign-in required) and save it, unrenamed, as
`data/raw/IHME_GBD_2023_DEMOGRAPHICS_1950_2023_TMRLT_Y2025M06D09.CSV`.

### Optional: the GBD 2019 relative-risk workbook

Only needed to regenerate the curated age-attenuation tables, which is a
deliberate act and not part of a normal build. Download *"Relative risks: all
risk factors except for ambient air pollution, alcohol, smoking, and
temperature [XLSX]"* from the
[GBD 2019 Relative Risks record](https://ghdx.healthdata.org/record/ihme-data/gbd-2019-relative-risks)
and save it, unrenamed, as
`data/raw/IHME_GBD_2019_RELATIVE_RISKS_Y2020M10D15.XLSX`.

## What downloads by itself

| Input | Source | Notes |
|-------|--------|-------|
| Cause-specific mortality | WHO GHE 2021 via the GHO OData API | One request per cause and sex, so the API's `$top` cap cannot silently truncate |
| Population, abridged life tables | UN WPP 2024, medium variant | Two gzipped CSVs |
| Dietary dose–response curves | IHME Burden-of-Proof public JSON endpoints | No login; cached at `data/raw/bop_rr_curves.csv` |
| Sodium and SBP curves | Same Burden-of-Proof API | Four curves, units and evidence stars validated |
| Location hierarchy | Public IHME GBD 2021 hierarchy | Falls back to the bundled national mortality list |
| GDD-IA calorie table | Zenodo record 10.5281/zenodo.20818140 | 83 MB, verified against Zenodo's MD5 |

Responses from the IHME and WHO APIs are validated against strict Pydantic
schemas in `tools/source_schemas.py` the moment they arrive, before any
dataframe work. The Burden-of-Proof endpoints sit behind Cloudflare's edge
bot-check, which a normal browser User-Agent passes; automated cloud IPs may
get a 403, in which case run the tool once from an ordinary machine and the
cached curves are reused afterwards.

## The stages

`tools/build_data.py` runs these in order, each into a staging directory:

| Stage | Builder | Produces |
|-------|---------|----------|
| Direct exposure baseline | `build_baseline_exposure.py` | `baseline_exposure.csv` |
| Calorie baseline | `build_baseline_calories.py` | `baseline_calories.csv` |
| Health and demographic data | `prepare_data.py` | `relative_risks.csv`, `mortality.csv`, `population.csv`, `local_life_table.csv`, `standard_life_table.csv` |
| Sodium mediator baseline | `build_baseline_mediators_from_gbd.py` | `baseline_mediators.csv` |
| Sodium and SBP relative risks | `build_sodium_relative_risks.py` | `sodium_relative_risks.csv` |

Each stage declares its outputs, and `run_stage` fails loudly if a builder
returns without writing one. [Data sources](../model/data_sources.md) describes
what each output contains and where its numbers come from.

## Curated reference tables

Three tables under `tools/reference/` are checked in rather than derived,
because their sources are either not machine-readable or not reproducible from
a public API:

- `rr_age_attenuation.csv` and `sbp_age_attenuation.csv` — per-age log-RR shapes
  from the GBD 2019 relative-risk workbook, normalised at the 60–64 reference
  age. Regenerated by `tools/generate_rr_age_attenuation.py` and
  `tools/generate_sbp_age_attenuation.py`.
- `rr_tmrel.csv` — the GBD 2023 appendix Table 18 TMRELs at which each curve is
  clipped.
- `red_meat_rr_log_linear.csv` — literature log-linear red-meat curves.
- `sodium_to_sbp.json` — the reviewed sodium-to-SBP response coefficients, with
  published native units retained beside the canonical values.
  `tools/validate_sodium_coefficients.py` checks every unit conversion and can
  verify reviewed source-file hashes with `--source-dir`.
- `baseline_country_sources.csv` — the 175-country target set with its explicit
  GBD and calorie source proxies.

The two `generate_*_age_attenuation.py` tools are one-off builders. Run them
only when deliberately refreshing the donor workbook, and commit the resulting
table as a reviewed change.

## Verifying a rebuild

The builders sort their output and pin the float format, so a rebuild from
unchanged inputs should reproduce the committed CSVs byte for byte. Check that
directly:

```bash
uv run python -m tools.build_data
git diff --stat src/mealhealth/data/
```

A non-empty diff means an upstream file changed, a pinned digest was updated,
or a builder's behaviour changed — all three deserve a look before committing.
Then run the suite: `uv run pytest -q` reads the bundled data and will catch
coverage or unit regressions.
