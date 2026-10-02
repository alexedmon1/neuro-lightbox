"""Profiles: selection, discovery, and a core that works without one's knowledge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from neuro_lightbox import profiles
from neuro_lightbox.cli import main
from neuro_lightbox.profiles import Profile, get_profile


class PlainProfile(Profile):
    """A profile that knows nothing: every hook at its neutral default."""

    name = "plain"


@pytest.fixture
def plain(monkeypatch):
    monkeypatch.setitem(profiles._BUILTIN, "plain", "tests.test_profiles:PlainProfile")
    monkeypatch.delitem(profiles._LOADED, "plain", raising=False)
    yield get_profile("plain")
    profiles._LOADED.pop("plain", None)


def _results(root: Path) -> Path:
    d = root / "tables" / "rsfmri" / "trajectory"
    d.mkdir(parents=True)
    (d / "effects.csv").write_text("test,measure,d,p\nchange,ReHo,0.4,0.03\n")
    (d / "provenance.json").write_text(json.dumps({"tools": [{"name": "pkg", "version": "1"}]}))
    return root


def test_the_default_profile_is_eeg():
    assert get_profile().name == "eeg"
    assert get_profile(None) is get_profile("eeg")


def test_an_unknown_profile_is_a_clean_error(tmp_path):
    res = CliRunner().invoke(main, ["build", "--profile", "nope", "--output", str(tmp_path)])
    assert res.exit_code == 1
    assert "unknown profile 'nope'" in res.output


def test_the_study_config_selects_the_profile(tmp_path):
    cfg = tmp_path / "study.yaml"
    cfg.write_text("profile: from_the_study\npaths: {gallery: ./g}\n")
    res = CliRunner().invoke(main, ["build", "--config", str(cfg)])
    assert res.exit_code == 1
    assert "unknown profile 'from_the_study'" in res.output


def test_an_option_of_another_profile_is_refused(plain, tmp_path):
    res = CliRunner().invoke(main, ["build", "--profile", "plain", "--output", str(tmp_path),
                                    "--localization", str(tmp_path)])
    assert res.exit_code == 1
    assert "--localization is not an option of the plain profile" in res.output


def test_installed_profiles_are_discovered(monkeypatch):
    class EP:
        def __init__(self, name, value):
            self.name, self.value = name, value

    monkeypatch.setattr(profiles.metadata, "entry_points",
                        lambda group=None: [EP("mri", "pkg.lightbox:MriProfile"),
                                            EP("eeg", "elsewhere:Other")])
    found = profiles.available()
    assert found["mri"] == "pkg.lightbox:MriProfile"
    assert found["eeg"] == "neuro_lightbox.profiles.eeg:EegProfile", "a built-in is not replaced"


def test_a_profile_that_knows_nothing_still_builds_a_gallery(plain, tmp_path):
    from neuro_lightbox.builder import build
    from neuro_lightbox.config import BuildConfig, SourceInput

    out = tmp_path / "gallery"
    build(BuildConfig(output_dir=out, results=[SourceInput(_results(tmp_path / "r"), "R")],
                      profile="plain", thumb_workers=1), verbose=False)
    manifest = json.loads((out / "data" / "manifest.json").read_text())
    entry = manifest["paradigms"]["rsfmri"]["trajectory"]
    assert manifest["title"] == "Gallery"
    assert "localization" not in manifest, "no inputs side without a profile that has one"
    assert entry["tables"]["R"][0]["rows"] == [["change", "ReHo", "0.4", "0.03"]]
    assert entry["figures"] == {}, "no renderers, no figures"
    assert entry["summary"] is None
    assert entry["meta"]["domain"] == "Other"
    assert entry["provenance"] == {"tools": [{"name": "pkg", "version": "1"}]}
    assert json.loads((out / "data" / "profile.json").read_text()) == {
        "name": "plain", "vocabulary": {}}


def test_the_app_runs_on_an_empty_vocabulary(plain, tmp_path):
    from neuro_lightbox.builder import build
    from neuro_lightbox.config import BuildConfig, SourceInput
    from tests.test_app_dom import _node_env, snapshot

    env = _node_env()
    if env is None:
        pytest.skip("needs node and jsdom (npm install --prefix tests/js)")
    out = tmp_path / "gallery"
    build(BuildConfig(output_dir=out, results=[SourceInput(_results(tmp_path / "r"), "R")],
                      profile="plain", thumb_workers=1), verbose=False)
    pages = snapshot(out, env)          # fails on any error the app logs
    assert "title: Gallery" in pages
    assert "Effects" in pages, "the table is listed on its analysis page"
