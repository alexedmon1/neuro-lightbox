"""Every summary of every golden gallery keeps the reporting contract (plan §6, Phase 3).

For each analysis read from the results specification: the summary states the
correction the analysis records, and every row of every tests table is a row of
the summary — significant or not — with an effect and its interval where the
table has them, and a p of the kind the table names. The unit tests
(test_spec.py, test_contract.py) pin the wording; this checks it holds across
real-shaped output.
"""

from __future__ import annotations

import json
import re
from html import unescape

import pytest

from neuro_lightbox.scanner import _slugify
from neuro_lightbox.spec import find_analyses, load_analysis
from tests.test_golden import CASES, FIXTURES

_ROW = re.compile(r'<tr class="spec-(sig|null)">(.*?)</tr>', re.S)
_CELL = re.compile(r"<td>(.*?)</td>", re.S)


def _analyses(case, golden_build):
    gallery = golden_build(case)["_gallery"]
    manifest = json.loads((gallery / "data" / "manifest.json").read_text(encoding="utf-8"))
    for folder in find_analyses(FIXTURES / CASES[case][0] / "results"):
        spec = load_analysis(folder)
        entry = manifest["paradigms"][_slugify(spec.analysis_type)][_slugify(spec.id)]
        yield spec, entry["summary"] or ""


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_summary_states_the_recorded_correction(golden_build, case):
    problems = []
    for spec, html in _analyses(case, golden_build):
        statement = spec.record["inference"]["correction"]["statement"]
        if statement not in unescape(html):
            problems.append(f"{spec.id}: the correction statement is not in the summary")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("case", sorted(CASES))
def test_every_test_is_a_summary_row_with_effect_and_p(golden_build, case):
    problems = []
    for spec, html in _analyses(case, golden_build):
        tests = spec.tables_with_role("tests")
        n_rows = sum(len(t.read()[1]) for t in tests)
        rows = _ROW.findall(html)
        if len(rows) != n_rows:
            problems.append(f"{spec.id}: {n_rows} tests, {len(rows)} summary rows")
        for t in tests:
            kind = t.qualifier("p_value", "PKind")
            if f"p ({kind}" not in html:
                problems.append(f"{spec.id}: {t.path.name}: p's kind ({kind}) not stated")
        for _cls, row in rows:
            cells = [unescape(c) for c in _CELL.findall(row)]
            if not re.match(r"-?\d", cells[1]) or "[" not in cells[1]:
                problems.append(f"{spec.id}: a row without effect and interval: {cells[:2]}")
    assert not problems, "\n".join(problems[:20])
