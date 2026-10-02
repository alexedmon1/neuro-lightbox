"""The reporting contract (plan §6, Phase 3): what a digest must say about each result."""

from __future__ import annotations

from neuro_lightbox.contract import correction_statement, direction_text, effect_text, p_text
from neuro_lightbox.profiles.eeg.summarize import build_significance_summary


def _tbl(filename, header, rows):
    return {"filename": filename, "headers": header.split(","), "rows": [r.split(",") for r in rows]}


# --------------------------------------------------------------------------- #
# The words
# --------------------------------------------------------------------------- #
def test_a_correction_is_stated_never_assumed():
    assert correction_statement("fdr", "BH", "q") == "FDR (BH) q &lt; 0.05"
    assert correction_statement("uncorrected") == "uncorrected p &lt; 0.05"
    assert correction_statement(None) == "p &lt; 0.05, correction not recorded"
    assert "not recorded" in correction_statement("corrected")
    assert "FDR" not in correction_statement(None)


def test_an_effect_names_its_measure_and_interval():
    assert effect_text(-0.4, "g", (-0.8, -0.1), signed_magnitude=True) == "g = 0.40 [0.10, 0.80]"
    assert effect_text(0.05, "d", (-0.40, 0.51)) == "d = 0.05 [−0.40, 0.51]"
    assert effect_text(0.3, None) == "effect = 0.30", "an unrecorded measure is not named"


def test_p_text_uses_the_tests_own_symbol():
    assert p_text(0.0213, "q") == "q = .021"
    assert p_text(0.0004) == "p &lt; .001"


def test_direction_is_the_tests():
    assert direction_text("two_group", "KO", "WT") == "&#9650; = KO &gt; WT"
    assert direction_text("one_sample") == "&#9650; = increase"
    assert direction_text("omnibus") == "omnibus test, no direction"
    assert "not recorded" in direction_text(None)


# --------------------------------------------------------------------------- #
# The digests
# --------------------------------------------------------------------------- #
NATIVE = "hypothesis,kind,band,spatial,effect_size,effect_size_type,p_value,q_value,fdr_family,significant,group_a,group_b"


def test_fdr_is_named_with_its_method_from_the_table():
    tbl = _tbl("x_hypotheses.csv", NATIVE,
               ["disease_effect,contrast,Alpha,,0.9,hedges_g,0.001,0.004,scope=band method=BH,TRUE,KO,WT"])
    html = build_significance_summary([tbl])
    assert "FDR (BH) q &lt; 0.05" in html


def test_a_raw_p_is_never_called_fdr():
    """§2 defect 1: an uncorrected p read as "FDR q < 0.05"."""
    tbl = _tbl("summary_effects.csv", "hypothesis,band,effect_size,p_value",
               ["change__p60,ReHo,1.3,0.001", "change__p90,ReHo,0.1,0.8"])
    html = build_significance_summary([tbl])
    assert "FDR" not in html
    assert "p &lt; 0.05, correction not recorded" in html


def test_the_measure_comes_from_the_table():
    """§2 defect 2: every effect labelled Hedges g."""
    tbl = _tbl("x_hypotheses.csv", NATIVE,
               ["group_omnibus,omnibus,Alpha,,0.08,omega2_partial,0.01,0.02,method=BH,TRUE,,",
                "disease_effect,contrast,Alpha,,-0.9,hedges_g,0.001,0.004,method=BH,TRUE,KO,WT"])
    html = build_significance_summary([tbl])
    assert "&omega;&sup2;<sub>p</sub> = 0.08" in html, "omnibus: ω²p, no sign"
    assert "omnibus test, no direction" in html
    assert "g = 0.90" in html


def test_direction_reads_the_groups_and_otherwise_says_it_cannot():
    """§2 defect 3: two-group arrows on one-sample tests."""
    with_groups = _tbl("x_hypotheses.csv", NATIVE,
                       ["disease_effect,contrast,Alpha,,-0.9,hedges_g,0.001,0.004,method=BH,TRUE,KO,WT"])
    assert "&#9650; = KO &gt; WT" in build_significance_summary(
        [with_groups], group_labels={"KO": "KO"})
    bare = _tbl("summary_effects.csv", "hypothesis,band,effect_size,p_value",
                ["change__p60,ReHo,1.3,0.001"])
    html = build_significance_summary([bare])
    assert "first-listed group" not in html
    assert "the test's direction is not recorded" in html
    # the study's design names the groups when the table does not
    designed = build_significance_summary(
        [bare], contrast_design={"change__p60": {"group_a": "cpz", "group_b": "ctl"}},
        group_labels={"cpz": "Cuprizone", "ctl": "Control"})
    assert "&#9650; = Cuprizone &gt; Control" in designed


def test_a_null_keeps_its_magnitude():
    """§2 defect 4: "No significant effects" with no magnitude."""
    tbl = _tbl("x_hypotheses.csv", NATIVE,
               ["dose_icv,contrast,Alpha,,0.05,hedges_g,0.83,0.91,method=BH,FALSE,A,B",
                "dose_icv,contrast,Beta,,-0.31,hedges_g,0.20,0.40,method=BH,FALSE,A,B"])
    html = build_significance_summary([tbl])
    assert "No significant" not in html
    assert "n.s. — largest" in html and "g = 0.31" in html and "q = .400" in html
    assert "2 tests" in html


def test_an_equivalence_test_reports_equivalence():
    tbl = _tbl("x_hypotheses.csv", NATIVE + ",equivalent",
               ["hd_icv_normalization,equivalence,Alpha,,0.05,hedges_g,0.8,0.9,method=BH,FALSE,HD,WT,TRUE",
                "hd_icv_normalization,equivalence,Beta,,0.70,hedges_g,0.001,0.01,method=BH,TRUE,HD,WT,FALSE",
                "hd_icv_normalization,equivalence,Delta,,0.30,hedges_g,0.3,0.5,method=BH,FALSE,HD,WT,FALSE"])
    html = build_significance_summary([tbl])
    assert "equivalence test (TOST), HD vs WT" in html
    assert "equivalent within the study margin in 1 of 3 tests" in html
    assert "differs (FDR (BH) q &lt; 0.05) in 1" in html


def test_contrasts_follow_the_study_order():
    tbl = _tbl("x_global.csv", "hypothesis,band,effect_size,significant",
               ["c_third,Alpha,0.9,TRUE", "c_first,Alpha,0.5,TRUE", "c_second,Alpha,0.4,FALSE"])
    html = build_significance_summary([tbl], contrast_order=["c_first", "c_second", "c_third"])
    listing = html[html.index("</p>"):]
    assert listing.index("c_first") < listing.index("c_second") < listing.index("c_third")


def test_the_confirmatory_result_leads_and_counts_follow():
    tbl = _tbl("x_global.csv", "hypothesis,band,effect_size,significant",
               ["explore,Alpha,2.0,TRUE", "primary,Alpha,0.2,FALSE"])
    html = build_significance_summary([tbl], contrast_meta={"primary": {"role": "confirmatory"}})
    lead = html[:html.index("</p>")]
    assert lead.index("Confirmatory") < lead.index("of 2 tests")
    assert "(n.s.)" in lead, "a confirmatory null leads too, marked"


def test_without_a_confirmatory_test_the_largest_is_named_as_selected():
    tbl = _tbl("x_global.csv", "hypothesis,band,effect_size,significant",
               ["a,Alpha,2.0,TRUE", "b,Alpha,0.2,FALSE"])
    html = build_significance_summary([tbl])
    assert "Largest effect of 2 tests" in html
