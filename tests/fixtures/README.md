# Golden-build fixtures

Results trees that `tests/test_golden.py` builds whole galleries from. The
frozen builds are in `tests/golden/`; see that test's docstring for what is
compared and how to accept an intended change (`--update-golden`). Both are in
neurofaune's results specification (0.1.0) and both were written by neurofaune's
own writer (strict), so they conform by construction; check one with
`~/sandbox/neurofaune/.venv/bin/python -m neurofaune.results check <fixture>/results`.

| Fixture | What it is | Golden case |
|---|---|---|
| `mri_h1c/` | The cuprizone H1c export the source-lightbox feasibility test built (NEURO_LIGHTBOX_PLAN.md §2), rewritten in the specification by `mri_h1c/make_spec.py` from its synthetic tables (`mri_h1c/source/`): one ROI-level analysis, `roi/h1c_function_trajectory` — `tests_grey_matter.csv` (96 tests, headline), `tests_by_hemisphere.csv` (144, faceted left / right), `roi_posthoc.csv` (600 elements). `export_h1c.py` is the original export to source-lightbox's layout, kept as the record of where the structure came from. | `mri_h1c` |
| `mri_spec/` | Two analyses written from nothing by `make_mri_spec.py`: `tbss/demo` (two groups, FA / MD / MK, planted corpus-callosum and internal-capsule effects, FA null, with a background image) and `vbm/demo_change` (one-sample GM change, one planted blob, no background). Its docstring lists the planted truth. | `mri_spec` |

Both generators run with neurofaune's environment and are deterministic:

```bash
~/sandbox/neurofaune/.venv/bin/python tests/fixtures/make_mri_spec.py
~/sandbox/neurofaune/.venv/bin/python tests/fixtures/mri_h1c/make_spec.py
```

**The numbers are synthetic.** The study is unpublished and this repository is
public. `mri_h1c` keeps the export's structure — file and column names, contrast /
measure / ROI / group names, which rows exist, design counts (n per group, df) —
with every measured value (effects, statistics, p, intervals) replaced by a
synthetic one before it was first committed; its rewrite adds no value. `mri_spec`
is invented throughout. No fixture holds a local path.
