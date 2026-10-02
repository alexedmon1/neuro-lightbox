"""Every digest of every golden gallery keeps the reporting contract (plan §6, Phase 3).

For each comparison listed in a digest: what ▲ means for it, and a magnitude —
significant or not. For each digest: a correction statement that matches what
the analysis's tables record (FDR only where a table holds FDR-adjusted values;
"not recorded" where none records a correction), and comparisons in the study's
order. The unit tests (test_contract.py) pin the wording; this checks it holds
across real-shaped output.
"""

from __future__ import annotations

import csv
import json
import re
from html import unescape

import pytest

from tests.test_golden import CASES

_ITEM = re.compile(r"<li[^>]*>(.*?)</li>", re.S)
_LABEL = re.compile(r'<span class="sig-contrast">(.*?)</span>')
_MAGNITUDE = re.compile(r"= −?\d|-edge|\d+ (vertices|vertex|channels|channel|ROIs?)\b|"
                        r"no effect recorded|not recorded")
_FDR_COLUMNS = {"q_value", "p_fdr", "q_fdr"}
_CORRECTED_COLUMNS = _FDR_COLUMNS | {"p_corrected", "cluster_p", "component_p"}


def _digests(case, golden_build):
    gallery = golden_build(case)["_gallery"]
    manifest = json.loads((gallery / "data" / "manifest.json").read_text(encoding="utf-8"))
    for paradigm, analyses in manifest["paradigms"].items():
        for analysis, entry in analyses.items():
            html = entry.get("summary") or ""
            if 'class="sig-list"' not in html:
                continue                      # descriptive, no comparisons
            columns = set()
            for path in (gallery / "tables" / paradigm / analysis).glob("*.csv"):
                with open(path, newline="", encoding="utf-8") as f:
                    columns |= set(next(csv.reader(f), []))
            yield f"{paradigm}/{analysis}", html, columns, manifest


@pytest.mark.parametrize("case", sorted(CASES))
def test_every_comparison_states_direction_and_magnitude(golden_build, case):
    problems = []
    for name, html, _cols, _m in _digests(case, golden_build):
        for item in _ITEM.findall(html):
            label = unescape(_LABEL.search(item).group(1)) if _LABEL.search(item) else "?"
            if "sig-groups" not in item:
                problems.append(f"{name}: {label}: no direction key")
            if not _MAGNITUDE.search(unescape(re.sub(r"<[^>]+>", " ", item))):
                problems.append(f"{name}: {label}: no magnitude")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_correction_is_what_the_tables_record(golden_build, case):
    problems = []
    for name, html, columns, _m in _digests(case, golden_build):
        lead = unescape(html[:html.index("</p>")])
        if "FDR" in lead and not columns & _FDR_COLUMNS:
            problems.append(f"{name}: says FDR, but no table holds FDR-adjusted values")
        if (not columns & _CORRECTED_COLUMNS and "CI" not in lead
                and "permutation" not in lead and "not recorded" not in lead):
            problems.append(f"{name}: no table records a correction, and the lead does not say so")
        for phrase in ("No significant", "first-listed group"):
            if phrase in html:
                problems.append(f"{name}: still says {phrase!r}")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("case", sorted(CASES))
def test_comparisons_follow_the_study_order(golden_build, case):
    problems = []
    for name, html, _cols, manifest in _digests(case, golden_build):
        order = manifest.get("contrast_order") or []
        by_label = {}
        for c in order:
            by_label.setdefault(manifest["contrast_labels"].get(c, c), c)
        rank = {c: i for i, c in enumerate(order)}
        for ul in re.findall(r'<ul class="sig-list">(.*?)</ul>', html, re.S):
            names = [by_label.get(unescape(l), unescape(l)) for l in _LABEL.findall(ul)]
            ranks = [rank.get(n, len(order)) for n in names]
            if ranks != sorted(ranks):
                problems.append(f"{name}: {names}")
    assert not problems, "\n".join(problems)
