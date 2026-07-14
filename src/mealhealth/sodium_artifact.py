# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validated loader for compact sodium draw artifacts.

No production artifact is bundled yet.  This module pins the boundary between
source-data preparation and the numerical kernel so an artifact with mismatched
draws, undeclared provenance, or an unexpected dtype fails before assessment.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

import numpy as np

from .sodium import SodiumRuntimeInputs

SODIUM_ARTIFACT_SCHEMA_VERSION = 1
_METADATA_KEY = "metadata_json"
_GLOBAL_ARRAYS = {
    "draw_id",
    "recovery_fraction",
    "sodium_tmrel_g",
    "sodium_to_sbp_slope",
    "sbp_curve_exposure_mmhg",
    "sbp_curve_log_rr",
    "sbp_age_attenuation",
    "sodium_curve_exposure_g",
    "stomach_curve_log_rr",
}
_PROVENANCE_COMPONENTS = {
    "baseline_urinary_g",
    "sbp_mean_mmhg",
    "sbp_sd_mmhg",
    "recovery_fraction",
    "sodium_tmrel_g",
    "sodium_to_sbp_slope",
    "sbp_curve_log_rr",
    "sbp_age_attenuation",
    "stomach_curve_log_rr",
}
_PROVENANCE_KINDS = {
    "source_draws",
    "parametric_approximation",
    "correlation_scenario",
}


@dataclass(frozen=True)
class SodiumArtifactMetadata:
    schema_version: int
    model_version: str
    draw_count: int
    seed: int
    countries: tuple[str, ...]
    ages: tuple[str, ...]
    sexes: tuple[str, ...]
    sbp_distribution: str
    mediated_outcomes: tuple[str, ...]
    source_hashes: dict[str, str]
    component_provenance: dict[str, str]


@dataclass(frozen=True)
class LoadedSodiumArtifact:
    metadata: SodiumArtifactMetadata
    draw_id: np.ndarray
    inputs: SodiumRuntimeInputs


def load_sodium_draw_artifact(path: str | Path, country: str) -> LoadedSodiumArtifact:
    """Load and validate one country from a versioned compressed NPZ artifact."""

    country = str(country).upper()
    if not re.fullmatch(r"[A-Z0-9]{3}", country):
        raise ValueError("country must be a three-character uppercase code")

    with np.load(Path(path), allow_pickle=False) as archive:
        raw_metadata = _read_metadata(archive)
        metadata = _validate_metadata(raw_metadata)
        if country not in metadata.countries:
            raise KeyError(f"Sodium draw artifact has no country {country!r}")

        manifest = raw_metadata["arrays"]
        expected_arrays = _GLOBAL_ARRAYS | {
            _country_key(code) for code in metadata.countries
        }
        if set(manifest) != expected_arrays:
            missing = sorted(expected_arrays - set(manifest))
            extra = sorted(set(manifest) - expected_arrays)
            raise ValueError(
                f"Invalid sodium array manifest: missing={missing}, extra={extra}"
            )
        archive_arrays = set(archive.files) - {_METADATA_KEY}
        if archive_arrays != expected_arrays:
            missing = sorted(expected_arrays - archive_arrays)
            extra = sorted(archive_arrays - expected_arrays)
            raise ValueError(
                f"Invalid sodium archive members: missing={missing}, extra={extra}"
            )

        selected_keys = _GLOBAL_ARRAYS | {_country_key(country)}
        arrays = {
            name: _load_validated_array(archive, manifest, name)
            for name in selected_keys
        }

    draw_id = arrays["draw_id"]
    if draw_id.ndim != 1 or draw_id.shape != (metadata.draw_count,):
        raise ValueError("draw_id must have shape (draw_count,)")
    if draw_id.dtype.kind not in "iu":
        raise ValueError("draw_id must use an integer dtype")
    if np.unique(draw_id).size != metadata.draw_count:
        raise ValueError("draw_id values must be unique")

    country_values = arrays[_country_key(country)]
    expected_country_shape = (
        metadata.draw_count,
        len(metadata.ages),
        len(metadata.sexes),
        3,
    )
    if country_values.shape != expected_country_shape:
        raise ValueError(
            f"{_country_key(country)} must have shape {expected_country_shape}, "
            f"got {country_values.shape}"
        )

    inputs = SodiumRuntimeInputs(
        baseline_urinary_g=country_values[..., 0],
        sbp_mean_mmhg=country_values[..., 1],
        sbp_sd_mmhg=country_values[..., 2],
        recovery_fraction=arrays["recovery_fraction"],
        sodium_tmrel_g=arrays["sodium_tmrel_g"],
        sodium_to_sbp_slope=arrays["sodium_to_sbp_slope"],
        sbp_curve_exposure_mmhg=arrays["sbp_curve_exposure_mmhg"],
        sbp_curve_log_rr=arrays["sbp_curve_log_rr"],
        sbp_age_attenuation=arrays["sbp_age_attenuation"],
        mediated_outcomes=metadata.mediated_outcomes,
        sodium_curve_exposure_g=arrays["sodium_curve_exposure_g"],
        stomach_curve_log_rr=arrays["stomach_curve_log_rr"],
    )
    if inputs.baseline_urinary_g.shape[0] != metadata.draw_count:
        raise ValueError("country arrays and metadata draw_count disagree")
    return LoadedSodiumArtifact(metadata=metadata, draw_id=draw_id, inputs=inputs)


def _read_metadata(archive: np.lib.npyio.NpzFile) -> dict[str, Any]:
    if _METADATA_KEY not in archive.files:
        raise ValueError(f"Sodium draw artifact is missing {_METADATA_KEY}")
    encoded = archive[_METADATA_KEY]
    if encoded.shape != () or encoded.dtype.kind not in "US":
        raise ValueError("metadata_json must be a scalar Unicode/byte string")
    try:
        raw = encoded.item()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        metadata = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("metadata_json is not valid UTF-8 JSON") from exc
    if not isinstance(metadata, dict):
        raise ValueError("metadata_json must contain a JSON object")
    return metadata


def _validate_metadata(raw: dict[str, Any]) -> SodiumArtifactMetadata:
    required = {
        "schema_version",
        "model_version",
        "draw_count",
        "seed",
        "countries",
        "ages",
        "sexes",
        "sbp_distribution",
        "mediated_outcomes",
        "arrays",
        "source_hashes",
        "component_provenance",
    }
    if set(raw) != required:
        raise ValueError(
            "Invalid sodium metadata fields: "
            f"missing={sorted(required - set(raw))}, "
            f"extra={sorted(set(raw) - required)}"
        )
    if raw["schema_version"] != SODIUM_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported sodium artifact schema {raw['schema_version']!r}; "
            f"expected {SODIUM_ARTIFACT_SCHEMA_VERSION}"
        )
    if not isinstance(raw["model_version"], str) or not raw["model_version"]:
        raise ValueError("model_version must be a non-empty string")
    if not isinstance(raw["draw_count"], int) or raw["draw_count"] < 1:
        raise ValueError("draw_count must be a positive integer")
    if not isinstance(raw["seed"], int):
        raise ValueError("seed must be an integer")

    countries = _unique_strings(raw["countries"], "countries")
    if not all(re.fullmatch(r"[A-Z0-9]{3}", code) for code in countries):
        raise ValueError("countries must contain three-character uppercase codes")
    ages = _unique_strings(raw["ages"], "ages")
    sexes = _unique_strings(raw["sexes"], "sexes")
    if sexes != ("male", "female"):
        raise ValueError("sexes must be ordered as ['male', 'female']")
    if raw["sbp_distribution"] != "normal":
        raise ValueError(
            "Sodium artifact schema 1 supports only sbp_distribution='normal'"
        )
    outcomes = _unique_strings(raw["mediated_outcomes"], "mediated_outcomes")

    arrays = raw["arrays"]
    if not isinstance(arrays, dict):
        raise ValueError("arrays must be an object")
    for name, specification in arrays.items():
        if not isinstance(name, str) or not isinstance(specification, dict):
            raise ValueError("array manifest entries must be named objects")
        if set(specification) != {"dtype", "shape"}:
            raise ValueError(f"Invalid array specification for {name!r}")
        if not isinstance(specification["dtype"], str):
            raise ValueError(f"Array dtype for {name!r} must be a string")
        shape = specification["shape"]
        if not isinstance(shape, list) or not all(
            isinstance(size, int) and size >= 0 for size in shape
        ):
            raise ValueError(f"Array shape for {name!r} must be non-negative integers")

    source_hashes = raw["source_hashes"]
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("source_hashes must be a non-empty object")
    if not all(
        isinstance(name, str)
        and isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest)
        for name, digest in source_hashes.items()
    ):
        raise ValueError("source_hashes must map source names to lowercase SHA-256")

    provenance = raw["component_provenance"]
    if not isinstance(provenance, dict):
        raise ValueError("component_provenance must be an object")
    if not _PROVENANCE_COMPONENTS <= set(provenance):
        missing = sorted(_PROVENANCE_COMPONENTS - set(provenance))
        raise ValueError(f"component_provenance is missing {missing}")
    if not all(kind in _PROVENANCE_KINDS for kind in provenance.values()):
        raise ValueError(
            f"component_provenance values must be in {sorted(_PROVENANCE_KINDS)}"
        )

    return SodiumArtifactMetadata(
        schema_version=raw["schema_version"],
        model_version=raw["model_version"],
        draw_count=raw["draw_count"],
        seed=raw["seed"],
        countries=countries,
        ages=ages,
        sexes=sexes,
        sbp_distribution=raw["sbp_distribution"],
        mediated_outcomes=outcomes,
        source_hashes=dict(source_hashes),
        component_provenance=dict(provenance),
    )


def _unique_strings(value: Any, name: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ValueError(f"{name} must be a non-empty list of strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{name} values must be unique")
    return tuple(value)


def _load_validated_array(
    archive: np.lib.npyio.NpzFile,
    manifest: dict[str, Any],
    name: str,
) -> np.ndarray:
    value = archive[name]
    specification = manifest[name]
    expected_dtype = np.dtype(specification["dtype"])
    expected_shape = tuple(specification["shape"])
    if value.dtype != expected_dtype or value.shape != expected_shape:
        raise ValueError(
            f"Array {name!r} disagrees with its manifest: expected "
            f"dtype={expected_dtype}, shape={expected_shape}; got "
            f"dtype={value.dtype}, shape={value.shape}"
        )
    return value


def _country_key(country: str) -> str:
    return f"country_{country}"
