# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the automatic GDD-IA calorie-source download."""

import hashlib
import io

import pytest

from tools import build_baseline_calories as calories

PAYLOAD = b"type,unit,value\nprim,kcal/d,2000\n"
PAYLOAD_MD5 = hashlib.md5(PAYLOAD, usedforsecurity=False).hexdigest()


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _fake_urlopen(payload):
    def urlopen(request, timeout=None):
        urlopen.requested = request.full_url
        return _FakeResponse(payload)

    urlopen.requested = None
    return urlopen


def test_existing_source_is_not_downloaded(tmp_path, monkeypatch):
    staged = tmp_path / "GDD-IA-intake_kcals_2020.csv"
    staged.write_bytes(PAYLOAD)

    def fail(*args, **kwargs):
        raise AssertionError("a staged source must not be re-downloaded")

    monkeypatch.setattr(calories.urllib.request, "urlopen", fail)
    assert calories.ensure_source(staged) == staged
    assert staged.read_bytes() == PAYLOAD


def test_missing_source_is_downloaded_and_verified(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "GDD-IA-intake_kcals_2020.csv"
    urlopen = _fake_urlopen(PAYLOAD)
    monkeypatch.setattr(calories.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(calories, "GDD_IA_MD5", PAYLOAD_MD5)

    calories.ensure_source(target)

    assert target.read_bytes() == PAYLOAD
    assert urlopen.requested == calories.GDD_IA_URL


def test_checksum_mismatch_leaves_no_file(tmp_path, monkeypatch):
    target = tmp_path / "GDD-IA-intake_kcals_2020.csv"
    monkeypatch.setattr(calories.urllib.request, "urlopen", _fake_urlopen(b"truncated"))
    monkeypatch.setattr(calories, "GDD_IA_MD5", PAYLOAD_MD5)

    with pytest.raises(RuntimeError, match="Checksum mismatch"):
        calories.ensure_source(target)

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_pinned_url_points_at_the_pinned_record():
    assert calories.GDD_IA_RECORD in calories.GDD_IA_URL
    assert calories.GDD_IA_URL.endswith(f"/{calories.GDD_IA_FILENAME}/content")
