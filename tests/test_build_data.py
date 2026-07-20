# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the bundled-data build coordinator."""

import pytest

from tools import build_data


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


def test_builders_share_the_canonical_source_registry():
    assert (
        build_data.build_baseline_exposure.DIRECT_SOURCES
        is build_data.dietary_exposure_sources.DIRECT_SOURCES
    )


def test_manual_inputs_come_from_the_shared_source_registries():
    expected = {
        source.path(build_data.RAW)
        for source in (
            *build_data.dietary_exposure_sources.DIRECT_SOURCES.values(),
            *build_data.dietary_exposure_sources.MEDIATOR_SOURCES.values(),
        )
    }
    assert expected <= set(build_data.manual_inputs())


def test_missing_manual_inputs_are_reported(monkeypatch):
    missing = build_data.ROOT / "data" / "raw" / "example.csv"
    monkeypatch.setattr(build_data, "manual_inputs", lambda: (missing,))

    with pytest.raises(FileNotFoundError, match="example.csv"):
        build_data.check_manual_inputs()


def test_run_stage_rejects_a_runner_that_does_not_write(tmp_path):
    stage = build_data.Stage("no-op", lambda output_dir: None, ("expected.csv",))

    with pytest.raises(RuntimeError, match="expected.csv"):
        build_data.run_stage(stage, tmp_path)


def test_run_stage_accepts_an_output_written_to_staging(tmp_path):
    def write_output(output_dir):
        (output_dir / "expected.csv").write_text("new\n")

    stage = build_data.Stage("writer", write_output, ("expected.csv",))
    build_data.run_stage(stage, tmp_path)


def test_main_downloads_checks_and_runs_stages_in_order(monkeypatch):
    events = []

    monkeypatch.setattr(
        build_data.prepare_data,
        "ensure_raw_downloads",
        lambda: events.append("downloads"),
    )
    monkeypatch.setattr(
        build_data.build_baseline_calories,
        "ensure_source",
        lambda: events.append("calorie source"),
    )
    monkeypatch.setattr(
        build_data,
        "check_manual_inputs",
        lambda: events.append("check"),
    )
    monkeypatch.setattr(
        build_data,
        "run_stage",
        lambda stage, output_dir: events.append(stage.name),
    )
    monkeypatch.setattr(
        build_data,
        "publish_outputs",
        lambda stages, staging_dir: events.append("publish"),
    )

    build_data.main([])

    assert events == [
        "check",
        "downloads",
        "calorie source",
        *(stage.name for stage in build_data.STAGES),
        "publish",
    ]


def test_main_publishes_outputs_only_after_all_stages_succeed(monkeypatch, tmp_path):
    packaged_data = tmp_path / "package-data"

    def write_output(output_dir):
        (output_dir / "result.csv").write_text("new\n")

    monkeypatch.setattr(build_data, "PACKAGED_DATA", packaged_data)
    monkeypatch.setattr(
        build_data,
        "STAGES",
        (build_data.Stage("writer", write_output, ("result.csv",)),),
    )
    monkeypatch.setattr(build_data, "check_manual_inputs", lambda: None)
    monkeypatch.setattr(build_data.prepare_data, "ensure_raw_downloads", lambda: None)
    monkeypatch.setattr(
        build_data.build_baseline_calories, "ensure_source", lambda: None
    )

    build_data.main([])

    assert (packaged_data / "result.csv").read_text() == "new\n"


def test_publish_outputs_validates_every_file_before_replacing(monkeypatch, tmp_path):
    packaged_data = tmp_path / "package-data"
    packaged_data.mkdir()
    existing = packaged_data / "first.csv"
    existing.write_text("old\n")
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    (staging_dir / "first.csv").write_text("new\n")
    stages = (
        build_data.Stage("first", lambda output_dir: None, ("first.csv",)),
        build_data.Stage("second", lambda output_dir: None, ("second.csv",)),
    )
    monkeypatch.setattr(build_data, "PACKAGED_DATA", packaged_data)

    with pytest.raises(RuntimeError, match="second.csv"):
        build_data.publish_outputs(stages, staging_dir)

    assert existing.read_text() == "old\n"


def test_main_keeps_packaged_outputs_when_a_later_stage_fails(monkeypatch, tmp_path):
    packaged_data = tmp_path / "package-data"
    packaged_data.mkdir()
    existing = packaged_data / "result.csv"
    existing.write_text("old\n")

    def write_output(output_dir):
        (output_dir / "result.csv").write_text("new\n")

    def fail(output_dir):
        raise RuntimeError("stage failed")

    monkeypatch.setattr(build_data, "PACKAGED_DATA", packaged_data)
    monkeypatch.setattr(
        build_data,
        "STAGES",
        (
            build_data.Stage("writer", write_output, ("result.csv",)),
            build_data.Stage("failure", fail, ("other.csv",)),
        ),
    )
    monkeypatch.setattr(build_data, "check_manual_inputs", lambda: None)
    monkeypatch.setattr(build_data.prepare_data, "ensure_raw_downloads", lambda: None)
    monkeypatch.setattr(
        build_data.build_baseline_calories, "ensure_source", lambda: None
    )

    with pytest.raises(RuntimeError, match="stage failed"):
        build_data.main([])

    assert existing.read_text() == "old\n"


def test_list_inputs_reports_every_manual_file(monkeypatch, capsys):
    monkeypatch.setattr(
        build_data,
        "check_manual_inputs",
        lambda: pytest.fail("--list-inputs must not run the build"),
    )

    build_data.main(["--list-inputs"])

    out = capsys.readouterr().out
    for path in build_data.manual_inputs():
        assert str(path.relative_to(build_data.ROOT)) in out
    for digest in build_data.pinned_digests().values():
        assert digest in out
