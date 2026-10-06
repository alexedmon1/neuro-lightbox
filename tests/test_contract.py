"""The reporting contract (plan §6, Phase 3): what a digest must say about each result."""

from __future__ import annotations

from neuro_lightbox.contract import correction_statement, direction_text, effect_text, p_text


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
