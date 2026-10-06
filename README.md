# neuro-lightbox

A static gallery for MRI study results. It reads results written to
**neurofaune's results specification** — by neurofaune itself, by neurovrai, or
by a study's own scripts — and builds one folder of HTML, figures and tables that
opens from disk (`file://`) or from any web server ([`DEPLOY.md`](DEPLOY.md)).

*Derived from source-lightbox. EEG galleries are built by
[source-lightbox](https://github.com/alexedmon1/source-lightbox), developed on its
own; asking neuro-lightbox for its old `eeg` profile says so and stops. See
[`NEURO_LIGHTBOX_PLAN.md`](NEURO_LIGHTBOX_PLAN.md).*

---

## Quick start

```bash
cd ~/sandbox/neuro-lightbox && uv sync                 # install (one-time)
neuro-lightbox build --config /path/to/study.yaml --serve
#   builds the gallery folder named in the config, then serves it at
#   http://localhost:5500 (Ctrl+C to stop)
```

Or without a config:

```bash
neuro-lightbox build --results /path/to/results --label "TBSS" -o ./gallery
neuro-lightbox serve ./gallery        # serve it later
neuro-lightbox info  ./gallery        # what it holds
```

A minimal `study.yaml`:

```yaml
name: My study
profile: mri              # the default; the only built-in profile
paths:
  results: ./results      # a results root (or a list of {path, label})
  gallery: ./gallery
```

Paths are resolved relative to the config file.

---

## What it reads

The **results specification** is owned by neurofaune —
`docs/RESULTS_SPEC.md` (the format) and `docs/RESULTS_PRODUCERS.md` (how
neurofaune, neurovrai and study scripts write it) in
[neurofaune](https://github.com/alexedmon1/neurofaune). An analysis folder holds:

- `analysis.json` — what the analysis is: its type, measures and role
  (confirmatory / exploratory / …), the design, the inference, **the correction
  and what it is over**, the effect measure and its definition, every table with
  what one row of it is, every map, caveats;
- `provenance.json` — what produced it (package, version, commit), when, and
  whether the run finished;
- tables (CSV / TSV), each with a column dictionary beside it that maps its
  columns to a standard vocabulary (`effect_size`, `p_value` with its kind, …).

The gallery reads exactly what each `analysis.json` lists; nothing is inferred
from a column name, a filename or a folder. Every analysis folder under a results
root becomes one analysis of the gallery, grouped by its `analysis_type`. A
folder written to a specification version this reader does not know is skipped
with a warning. Check a folder before building with neurofaune's
`neurofaune results check <folder>`.

A results tree that is *not* written to the specification is still read by its
folder layout (`tables/<group>/<analysis>/*.csv`, `figures/<group>/<analysis>/`),
but gets its tables and figures only — no summary, because nothing in it says
what its columns mean.

---

## What each analysis shows

- **Summary.** The role, design, inference, the correction as the analysis states
  it and what it is corrected over, the effect and its definition, caveats and any
  decision rule. Then **every test that was run, significant or not**: effect with
  its interval, the direction it went, extent (for voxelwise tests), p with its
  kind, and n — significant rows in bold, nulls listed beside them. Clusters and
  elements are summarised largest first, with their count and a pointer to the full
  table; a cluster's effect is marked as selected.
- **Effect overview.** Tests by measure, each cell the test's effect, outlined
  where it is significant under the analysis's own correction and hatched wherever
  its interval includes 0 (the two are independent: a voxelwise test can pass while
  its whole-mask effect's interval spans 0).
- **Montages** (MRI profile). For every test with significant voxels, axial
  slices through their extent, the statistic on the analysis's background image
  (else its mask); a TBSS skeleton is thickened for display. A p map that does not
  say whether it holds p or 1 − p is not thresholded.
- **Tables**, sortable, with the full CSV and its column dictionary in the
  gallery's `tables/` folder.
- **What produced this** — the provenance strip; a run that did not finish is
  flagged.

---

## Profiles

The core (scanning, reading the specification, summaries, the effect overview,
the manifest, the app) knows no domain; a **profile** adds one. The built-in
profile is `mri`: measure definitions, display names of the analysis types, and
montages. A package can add a profile through the `neuro_lightbox.profiles`
entry-point group, naming a `neuro_lightbox.profiles.Profile` subclass; select it
with `profile:` in the study config or `--profile`.

---

## Development

```bash
.venv/bin/python -m pytest -q                   # the suite, golden builds included
.venv/bin/python -m pytest -q --update-golden   # accept an intended change; review git diff tests/golden/
```

Golden builds (`tests/golden/`) are whole galleries built from the fixtures in
`tests/fixtures/` (see its README). **This repository is public and the studies
behind the fixtures are unpublished: every value in a fixture is synthetic, and
no real value or local path is ever committed.** `tests/test_core_purity.py`
keeps any one domain out of the core and EEG out of the package.

## More

- **Hosting on a LAN/workstation (nginx):** [`DEPLOY.md`](DEPLOY.md)
- **Design notes:** [`DESIGN_NOTES.md`](DESIGN_NOTES.md)
