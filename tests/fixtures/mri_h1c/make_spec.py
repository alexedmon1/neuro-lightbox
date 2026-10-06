"""Write ``mri_h1c/results/``: the H1c fixture in neurofaune's results specification.

The input is ``source/`` — the cuprizone H1c export the source-lightbox feasibility
test built (NEURO_LIGHTBOX_PLAN.md §2), in source-analytics' table layout, with
every measured value already replaced by a synthetic one. Nothing here adds a
value: rows are regrouped into the specification's tables and their columns
described. Written by neurofaune's own writer (strict), so the folder conforms by
construction.

Rerun with neurofaune's environment::

    ~/sandbox/neurofaune/.venv/bin/python tests/fixtures/mri_h1c/make_spec.py
    ~/sandbox/neurofaune/.venv/bin/python -m neurofaune.results check tests/fixtures/mri_h1c/results

The analysis (one folder, ``roi/h1c_function_trajectory``):

* ``tests_grey_matter.csv`` (tests, headline): every measure's grey-matter-wide
  summary (GM_all for ReHo / fALFF and their z-scored versions, FC_mean and
  FC_homotopic for connectivity) in each of the twelve contrasts — 96 tests.
* ``tests_by_hemisphere.csv`` (tests): the left / right summaries (GM_L / GM_R,
  FC_left / FC_right) — 144 tests, faceted by hemisphere.
* ``roi_posthoc.csv`` (elements): the post hoc ROI rows — 600.

The export carries Cohen's d without an interval, and a 95% bootstrap interval on
the raw contrast estimate; the tests tables report the estimate with its interval
as the effect and keep d beside it, described.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from neurofaune.results import provenance, write_analysis, write_columns

HERE = Path(__file__).parent
SOURCE = HERE / "source"
OUT = HERE / "results" / "roi" / "h1c_function_trajectory"

MEASURES = ["ReHo", "fALFF", "FC_mean_gsr", "FC_homotopic_gsr",
            "ReHo_zscore", "fALFF_zscore", "FC_mean_nogsr", "FC_homotopic_nogsr"]
WIDE = {"GM_all", "FC_mean", "FC_homotopic"}
HEMISPHERE = {"GM_L": "left", "GM_R": "right", "FC_left": "left", "FC_right": "right"}
CONTRASTS = [f"{t}__{w}" for t in ("change_group", "change_cuprizone", "change_control")
             for w in ("p60_to_p90", "p60_to_p120", "p90_to_p120")] + [f"cross__{p}" for p in
                                                                    ("p60", "p90", "p120")]
WINDOWS = {"p60_to_p90": "p60→p90", "p90_to_p120": "p90→p120", "p60_to_p120": "p60→p120"}
GROUP_WORD = {"change_cuprizone": "Cuprizone", "change_control": "Control"}

COLUMNS = {
    "measure": {"Description": "the measure: ReHo, fALFF (raw ROI means; primary), their within-brain "
                               "z-scored versions (sensitivity), and per-animal summaries of the "
                               "Fisher-z connectivity matrix with / without global signal regression",
                "Standard": "measure"},
    "contrast": {"Description": "the test, as <test>__<level>", "Standard": "contrast"},
    "contrast_label": {"Description": "the contrast in words", "Standard": "contrast_label"},
    "facet": {"Description": "hemisphere of the summary", "Standard": "facet",
              "Levels": {"left": "left hemisphere", "right": "right hemisphere"}},
    "variable": {"Description": "the summary tested",
                 "Levels": {"GM_all": "mean over the grey-matter ROIs",
                            "GM_L": "mean over the left grey-matter ROIs",
                            "GM_R": "mean over the right grey-matter ROIs",
                            "FC_mean": "mean connectivity over all grey-matter edges",
                            "FC_left": "mean connectivity within the left hemisphere",
                            "FC_right": "mean connectivity within the right hemisphere",
                            "FC_homotopic": "mean connectivity over left-right homologue pairs"}},
    "element": {"Description": "the ROI (node_: an ROI's mean connectivity to the rest)",
                "Standard": "element"},
    "test": {"Description": "which test",
             "Levels": {"change_cuprizone": "the cuprizone group's within-animal change",
                        "change_control": "the control group's within-animal change",
                        "change_group": "the group difference in within-animal change",
                        "cross": "the group difference at one timepoint (diagnostic)"}},
    "level": {"Description": "the window (change tests) or the timepoint (cross)"},
    "test_kind": {"Description": "one-sample (a group's change) or two-group", "Standard": "test_kind"},
    "tested_direction": {"Description": "what a positive statistic means", "Standard": "tested_direction"},
    "observed_direction": {"Description": "the direction the contrast estimate went",
                           "Standard": "observed_direction"},
    "group_a": {"Description": "two-group tests: the group higher when the statistic is positive",
                "Standard": "group_a"},
    "group_b": {"Description": "two-group tests: the other group", "Standard": "group_b"},
    "n": {"Description": "animals in the test", "Standard": "n"},
    "n_cuprizone": {"Description": "cuprizone animals in the test"},
    "n_control": {"Description": "control animals in the test"},
    "df": {"Description": "error degrees of freedom of the cohort model", "Standard": "df"},
    "estimate": {"Description": "the contrast estimate in the measure's own units: mean within-animal "
                                "change, or cuprizone minus control", "Standard": "effect_size",
                 "EffectMeasure": "contrast estimate", "EffectScope": "the summary's own units"},
    "ci95_low": {"Description": "lower bound of the estimate's 95% bootstrap interval",
                 "Standard": "effect_ci_low", "CILevel": 0.95},
    "ci95_high": {"Description": "upper bound of the estimate's 95% bootstrap interval",
                  "Standard": "effect_ci_high", "CILevel": 0.95},
    "se": {"Description": "standard error of the estimate (cohort model)"},
    "t": {"Description": "t of the contrast (cohort model)", "Standard": "stat", "StatName": "t"},
    "p": {"Description": "p of the contrast from the cohort model's t, uncorrected",
          "Standard": "p_value", "PKind": "uncorrected", "PScope": "this test"},
    "d": {"Description": "Cohen's d, pooled SD, on per-animal values, ignoring cohort (no interval "
                         "recorded)"},
    "mean_cuprizone": {"Description": "mean of the cuprizone animals (empty where the test has none)"},
    "mean_control": {"Description": "mean of the control animals (empty where the test has none)"},
    **{f"{k}_{c}": {"Description": f"{'d' if k == 'd' else 'animals'} in cuprizone cohort {c} "
                                   f"{'against all controls' if k == 'd' else ''}".strip()}
       for c in "XYZ" for k in ("d", "n")},
    "adj_estimate": {"Description": "change-group tests: the estimate adjusted for each animal's "
                                    "baseline (change ~ cohort + baseline)"},
    "adj_se": {"Description": "standard error of adj_estimate"},
    "adj_t": {"Description": "t of adj_estimate"},
    "adj_p": {"Description": "p of adj_estimate, uncorrected", "PKind": "uncorrected"},
    "adj_df": {"Description": "degrees of freedom of adj_estimate"},
}
ROI_COLUMNS = {**COLUMNS,
               "estimate": {"Description": "the contrast estimate in the measure's own units",
                            "Standard": "estimate"},
               "d": {"Description": "Cohen's d, pooled SD, on per-animal ROI values, ignoring cohort",
                     "Standard": "effect_size", "EffectMeasure": "d", "EffectScope": "one ROI"}}


def label(test: str, level: str) -> str:
    if test == "cross":
        return f"Cuprizone vs control, {level}"
    if test == "change_group":
        return f"Cuprizone vs control: change, {WINDOWS[level]}"
    return f"{GROUP_WORD[test]}: change, {WINDOWS[level]}"


def common(d: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"measure": d["measure"], "contrast": d["test"] + "__" + d["level"],
                        "contrast_label": [label(t, lv) for t, lv in zip(d["test"], d["level"])]})
    two = d["test"].isin(["change_group", "cross"])
    out["test"], out["level"] = d["test"], d["level"]
    out["test_kind"] = ["two_group" if x else "one_sample" for x in two]
    out["tested_direction"] = ["cuprizone > control" if x else f"{GROUP_WORD[t].lower()}: mean change > 0"
                               for x, t in zip(two, d["test"])]
    out["observed_direction"] = [
        ("cuprizone > control" if e > 0 else "control > cuprizone") if x else
        (f"{GROUP_WORD[t].lower()}: increase" if e > 0 else f"{GROUP_WORD[t].lower()}: decrease")
        for x, t, e in zip(two, d["test"], d["estimate"])]
    out["group_a"] = ["cuprizone" if x else "" for x in two]
    out["group_b"] = ["control" if x else "" for x in two]
    out["n"] = d["n_cuprizone"] + d["n_control"]
    for c in ("n_cuprizone", "n_control", "df", "estimate"):
        out[c] = d[c]
    return out


def tests_table(d: pd.DataFrame, facet: bool) -> pd.DataFrame:
    out = common(d)
    if facet:
        out.insert(3, "facet", d["variable"].map(HEMISPHERE))
    out.insert(4 if facet else 3, "variable", d["variable"])
    for c in ("ci95_low", "ci95_high", "se", "t", "p", "d", "mean_cuprizone", "mean_control",
              "d_X", "n_X", "d_Y", "n_Y", "d_Z", "n_Z", "adj_estimate", "adj_se", "adj_t", "adj_p",
              "adj_df"):
        out[c] = d[c]
    return in_order(out)


def in_order(out: pd.DataFrame) -> pd.DataFrame:
    """Contrasts in the study's order (study.yaml), measures in MEASURES' order."""
    rank = {"contrast": {c: i for i, c in enumerate(CONTRASTS)},
            "measure": {m: i for i, m in enumerate(MEASURES)}}
    keys = ["contrast", "facet", "measure"] if "facet" in out else ["contrast", "measure"]
    return out.sort_values(keys, key=lambda s: s.map(rank[s.name]) if s.name in rank else s,
                           kind="stable").reset_index(drop=True)


def roi_table(d: pd.DataFrame) -> pd.DataFrame:
    out = common(d)
    out.insert(3, "element", d["variable"])
    for c in ("se", "t", "p", "d", "mean_cuprizone", "mean_control",
              "d_X", "n_X", "d_Y", "n_Y", "d_Z", "n_Z"):
        out[c] = d[c]
    return in_order(out)


def main() -> None:
    summary = pd.read_csv(SOURCE / "h1c_effect_size_summary.csv")
    roi = pd.read_csv(SOURCE / "h1c_posthoc_roi.csv")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    wide = tests_table(summary[summary.variable.isin(WIDE)], facet=False)
    hemi = tests_table(summary[summary.variable.isin(HEMISPHERE)], facet=True)
    rois = roi_table(roi)
    assert len(wide) + len(hemi) == len(summary), "every summary row lands in one tests table"
    tables = [("tests_grey_matter.csv", wide, COLUMNS), ("tests_by_hemisphere.csv", hemi, COLUMNS),
              ("roi_posthoc.csv", rois, ROI_COLUMNS)]
    for name, df, cols in tables:
        df.to_csv(OUT / name, index=False)
        write_columns(OUT / name, cols)

    analysis = {
        "id": "roi/h1c_function_trajectory",
        "title": "H1c: functional change over grey-matter ROIs (synthetic)",
        "description": "Within-animal change in ReHo, fALFF and functional connectivity summaries over "
                       "the atlas grey matter, and the group difference in that change, over three "
                       "windows, with the cross-sectional contrasts as diagnostics.",
        "analysis_type": "roi", "modality": "func", "measures": MEASURES, "role": "confirmatory",
        "design": {"n": 34, "groups": {"cuprizone": 24, "control": 10},
                   "test_kinds": ["one_sample", "two_group"]},
        "inference": {"method": "per test, a linear model with the cuprizone cohort modelled "
                                "(size-weighted); t test of the contrast",
                      "correction": {"p_kind": "uncorrected", "alpha": 0.05,
                                     "family": "none: each test on its own; the ROI rows are post hoc",
                                     "statement": "p per test from the cohort model's t, uncorrected "
                                                  "across tests, measures and ROIs"}},
        "effect": {"measure": "contrast estimate", "ci_level": 0.95,
                   "scope": "grey-matter-wide and hemisphere summaries (tests); one ROI (ROI rows: d)",
                   "definition": "the contrast in the measure's own units (mean change, or cuprizone "
                                 "minus control) with a 95% bootstrap interval; Cohen's d (pooled SD, "
                                 "ignoring cohort) is beside it, without an interval"},
        "tables": [
            {"path": "tests_grey_matter.csv", "role": "tests", "headline": True, "n_rows": len(wide),
             "rows": "one measure's grey-matter-wide summary in one contrast",
             "description": "every measure and contrast, significant or not"},
            {"path": "tests_by_hemisphere.csv", "role": "tests", "n_rows": len(hemi),
             "rows": "one measure's left or right summary in one contrast",
             "description": "the same tests, per hemisphere"},
            {"path": "roi_posthoc.csv", "role": "elements", "n_rows": len(rois),
             "rows": "one ROI in one measure and contrast (post hoc)",
             "description": "post hoc ROI rows"},
        ],
        "caveats": [
            "Every value is synthetic (tests/fixtures/mri_h1c/make_spec.py); only the structure is "
            "the H1c export's.",
            "Only the group difference in change over p60→p120 is the registered test; the other "
            "contrasts are descriptive.",
            "Cohen's d carries no interval in this export, so the summary reports the contrast "
            "estimate with its bootstrap interval.",
        ],
    }
    prov = provenance(
        [{"Name": "h1_function_trajectory.py", "Version": "study 9958868",
          "Description": "the study's own orchestration"},
         {"Name": "neurofaune", "Version": "8ba584e"}],
        status="completed", start="2026-10-02T09:16:28-04:00", end="2026-10-02T09:16:28-04:00",
        subjects={"n": 34, "groups": {"cuprizone": 24, "control": 10}})
    prov["environment"] = {"platform": "Linux"}
    report = write_analysis(OUT, analysis, prov)
    print("OK" if report.ok else report.errors, report.warnings)
    print(json.dumps({name: len(df) for name, df, _ in tables}))


if __name__ == "__main__":
    main()
