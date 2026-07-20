# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the bundled-data build coordinator."""

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "tools" / "build_data.py"
SPEC = importlib.util.spec_from_file_location("build_data", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
build_data = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = build_data
SPEC.loader.exec_module(build_data)


def test_stages_are_in_dependency_order():
    assert [stage.name for stage in build_data.STAGES] == [
        "direct exposure baseline",
        "calorie baseline",
        "health and demographic data",
        "sodium mediator baseline",
        "sodium and SBP relative risks",
    ]
    assert all(callable(stage.runner) for stage in build_data.STAGES)
    assert "baseline_exposure.csv" in build_data.STAGES[0].outputs
    assert "relative_risks.csv" in build_data.STAGES[2].outputs


def test_missing_manual_inputs_are_reported(monkeypatch):
    missing = build_data.ROOT / "data" / "raw" / "example.csv"
    monkeypatch.setattr(build_data, "manual_inputs", lambda: (missing,))

    with pytest.raises(FileNotFoundError, match="example.csv"):
        build_data.check_manual_inputs()


def test_main_downloads_checks_and_runs_stages_in_order(monkeypatch):
    events = []

    monkeypatch.setattr(
        build_data.prepare_data,
        "ensure_raw_downloads",
        lambda: events.append("downloads"),
    )
    monkeypatch.setattr(
        build_data,
        "check_manual_inputs",
        lambda: events.append("check"),
    )
    monkeypatch.setattr(
        build_data,
        "run_stage",
        lambda stage: events.append(stage.name),
    )

    build_data.main()

    assert events == [
        "check",
        "downloads",
        *(stage.name for stage in build_data.STAGES),
    ]
