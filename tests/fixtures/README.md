# Golden-build fixtures

Results trees that `tests/test_golden.py` builds whole galleries from. The
frozen builds are in `tests/golden/`; see that test's docstring for what is
compared and how to accept an intended change (`--update-golden`).

| Fixture | What it is | Golden cases |
|---|---|---|
| `eeg/` | The FORGE treatment study's source-analytics tree (analyses-v2, v0.7.1): three paradigms, 13 analyses, two localization pipelines with QC. | `eeg` (with the stand-in source-analytics interpreter), `eeg_no_sa` (without one) |
| `eeg_legacy/` | Output neither real tree has: the retired vertex modules published with `include_retired`, legacy column names, plugin provenance, two results trees compared side by side. Written from nothing. | `eeg_legacy` |
| `mri_h1c/` | The cuprizone H1c export the source-lightbox feasibility test built (NEURO_LIGHTBOX_PLAN.md §2), with `export_h1c.py`, the column mapping it used. | `mri_h1c` |
| `mri_spec/` | Two analyses in neurofaune's results specification (0.1.0): `tbss/demo` (two groups, FA / MD / MK, planted corpus-callosum and internal-capsule effects, FA null, with a background image) and `vbm/demo_change` (one-sample GM change, one planted blob, no background). Wholly synthetic — invented subjects, planted effects — and written by neurofaune's own writer (`read_randomise` + `write_readout_results`, strict), so it conforms by construction. | — |

`make_fixtures.py` wrote the first three and says how; rerunning it needs the
source trees, and is only for changing what the fixtures contain.
`make_mri_spec.py` writes `mri_spec/` from nothing, deterministically, with
neurofaune's environment (`~/sandbox/neurofaune/.venv/bin/python
tests/fixtures/make_mri_spec.py`); its docstring lists the planted truth.

**The numbers are synthetic.** Both studies are unpublished and this repository
is public. The fixtures keep each tree's structure — layout, file and column
names, contrast / band / ROI / group names, which rows exist, design counts
(n per group, df, permutations) — and replace every measured value (effects,
statistics, p / q, CIs, accuracies, component and cluster sizes, result flags)
with a coherent synthetic one. Rows were chosen (six ROIs, six channels, at most
60 rows a table spread across contrasts) before any value was synthesised. Image
files are small placeholders under their real names.

`eeg/sa_python` stands in for the source-analytics interpreter: it serves
`analysis_meta.json` (source-analytics v0.8.2's `analysis_meta()`), answers the
import probes, and answers each mosaic / circos worker call with a placeholder
PNG, logging the call's payload when `FAKE_SA_LOG` is set.
