# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Schema and alignment tests for compact sodium draw artifacts."""

import json

import numpy as np
import pytest

from mealhealth.sodium_artifact import load_sodium_draw_artifact


def _artifact_parts():
    draws, ages, sexes, outcomes = 3, 2, 2, 1
    sbp_x = np.linspace(100.0, 180.0, 5, dtype=np.float32)
    sodium_x = np.linspace(1.0, 7.0, 4, dtype=np.float32)
    country = np.empty((draws, ages, sexes, 3), dtype=np.float32)
    country[..., 0] = 3.5
    country[..., 1] = 130.0
    country[..., 2] = 14.0
    arrays = {
        "draw_id": np.arange(draws, dtype=np.int32),
        "recovery_fraction": np.full(draws, 0.928, dtype=np.float32),
        "sodium_tmrel_g": np.linspace(1.0, 5.0, draws, dtype=np.float32),
        "sodium_to_sbp_slope": np.full(draws, 2.42, dtype=np.float32),
        "sbp_curve_exposure_mmhg": sbp_x,
        "sbp_curve_log_rr": np.broadcast_to(
            np.linspace(0.0, 1.0, sbp_x.size, dtype=np.float32),
            (draws, outcomes, sbp_x.size),
        ).copy(),
        "sbp_age_attenuation": np.ones((outcomes, ages), dtype=np.float32),
        "sodium_curve_exposure_g": sodium_x,
        "stomach_curve_log_rr": np.broadcast_to(
            np.linspace(0.0, 0.3, sodium_x.size, dtype=np.float32),
            (draws, sodium_x.size),
        ).copy(),
        "country_USA": country,
    }
    provenance_components = (
        "baseline_urinary_g",
        "sbp_mean_mmhg",
        "sbp_sd_mmhg",
        "recovery_fraction",
        "sodium_tmrel_g",
        "sodium_to_sbp_slope",
        "sbp_curve_log_rr",
        "sbp_age_attenuation",
        "stomach_curve_log_rr",
    )
    metadata = {
        "schema_version": 1,
        "model_version": "test-v1",
        "draw_count": draws,
        "seed": 123,
        "countries": ["USA"],
        "ages": ["25-29", "30-34"],
        "sexes": ["male", "female"],
        "sbp_distribution": "normal",
        "mediated_outcomes": ["ischemic_heart_disease"],
        "arrays": {
            name: {"dtype": str(value.dtype), "shape": list(value.shape)}
            for name, value in arrays.items()
        },
        "source_hashes": {"synthetic-test": "0" * 64},
        "component_provenance": {
            name: "parametric_approximation" for name in provenance_components
        },
    }
    return arrays, metadata


def _write_artifact(path, arrays, metadata):
    np.savez_compressed(path, metadata_json=np.array(json.dumps(metadata)), **arrays)


def test_valid_artifact_loads_one_country(tmp_path):
    arrays, metadata = _artifact_parts()
    path = tmp_path / "sodium_draws.npz"
    _write_artifact(path, arrays, metadata)
    loaded = load_sodium_draw_artifact(path, "usa")
    assert loaded.metadata.model_version == "test-v1"
    assert loaded.metadata.sbp_distribution == "normal"
    assert loaded.metadata.mediated_outcomes == ("ischemic_heart_disease",)
    assert np.array_equal(loaded.draw_id, np.arange(3, dtype=np.int32))
    assert loaded.inputs.baseline_urinary_g.shape == (3, 2, 2)
    assert loaded.inputs.sbp_curve_log_rr.shape == (3, 1, 5)


def test_missing_country_is_rejected(tmp_path):
    arrays, metadata = _artifact_parts()
    path = tmp_path / "sodium_draws.npz"
    _write_artifact(path, arrays, metadata)
    with pytest.raises(KeyError, match="FRA"):
        load_sodium_draw_artifact(path, "FRA")


def test_duplicate_draw_ids_are_rejected(tmp_path):
    arrays, metadata = _artifact_parts()
    arrays["draw_id"] = np.array([0, 0, 2], dtype=np.int32)
    path = tmp_path / "sodium_draws.npz"
    _write_artifact(path, arrays, metadata)
    with pytest.raises(ValueError, match="draw_id values must be unique"):
        load_sodium_draw_artifact(path, "USA")


def test_manifest_mismatch_is_rejected(tmp_path):
    arrays, metadata = _artifact_parts()
    metadata["arrays"]["recovery_fraction"]["shape"] = [4]
    path = tmp_path / "sodium_draws.npz"
    _write_artifact(path, arrays, metadata)
    with pytest.raises(ValueError, match="disagrees with its manifest"):
        load_sodium_draw_artifact(path, "USA")


def test_unlabelled_component_provenance_is_rejected(tmp_path):
    arrays, metadata = _artifact_parts()
    del metadata["component_provenance"]["sbp_sd_mmhg"]
    path = tmp_path / "sodium_draws.npz"
    _write_artifact(path, arrays, metadata)
    with pytest.raises(ValueError, match="component_provenance is missing"):
        load_sodium_draw_artifact(path, "USA")
