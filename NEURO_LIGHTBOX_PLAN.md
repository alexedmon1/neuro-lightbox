# neuro-lightbox — plan

**Status: Phases 0–1 done (2026-10-02); see §6.** Written 2026-10-02 from a
cuprizone (rat MRI) session, after a feasibility test built one MRI analysis
into a source-lightbox gallery; revised the same day with the author's two
principles (§1).

**Decision (author, 2026-10-02):** rename source-lightbox to **neuro-lightbox**
and generalise it **in one repository** (option 1), with a **profile
interface** inside it (option 3) so EEG and MRI are profiles of one core.
**Revised the same day:** the one repository is a new one,
`alexedmon1/neuro-lightbox`, carrying source-lightbox's full history;
source-lightbox is left as it is (frozen, archived later) rather than renamed,
so its URL does not redirect and its PR and issues stay with it. This is not
the fork rejected below: no work continues in source-lightbox, so there is
nothing to drift or merge.
Considered and not chosen:

- *Core + two thin packages* (`lightbox-core`, `source-lightbox`, an MRI
  package): clean names, but three repositories, and every core change needs a
  release and pin bumps in two places — too much release work for one developer.
  Revisit only if the profiles' dependencies genuinely diverge.
- *Plugin interface only, keep the name*: no fork, but "source" stays a
  misleading name for an MRI gallery.
- *Fork to neuro-lightbox, merge upstream periodically*: works while the copies
  barely differ; once the core is generalised the EEG and MRI copies of the same
  code drift and improvements stop flowing — the outcome to avoid.

The goal: **one static, browsable gallery for any neuro study, rebuilt from its
analysis outputs by one command, that reports results honestly** — every test
with its magnitude, direction, uncertainty and correction, null results
included — and says what produced each number.

---

## 1. Principles (author, 2026-10-02)

1. **Built for the analysis packages, not for a workflow tool.** neuro-lightbox
   exists to present what **source-analytics** (EEG) and **neurofaune** (MRI)
   produce. It has **no dependency on DUET**, nor on any study's own records,
   and no DUET concept shapes its design or its schema. DUET — or a study, or
   anything else — can *use* it by pointing it at a results tree; neuro-lightbox
   does not know who is calling.
2. **The packages' outputs are for everyone, not for the lightbox.** What
   neurofaune and source-analytics write must be usable by anyone — a pandas or
   R script, a statistician with a spreadsheet, another dashboard, a journal's
   data supplement — with no lightbox installed and no knowledge of it. So the
   **output format belongs to the analysis packages**: open file formats, a
   documented and versioned specification, self-describing tables, provenance
   included (§4). neuro-lightbox is **one consumer** of that specification. Two
   consequences:
   - nothing a producer writes may exist only to steer the lightbox (today's
     filename-based table priority — `_table_priority`, `render.py:611`, ranking
     `*_effect_size_summary.csv` over `*_posthoc_roi.csv` — is the kind of
     convention that moves into declared metadata anyone can read);
   - the lightbox may never be the only place a number or its meaning can be
     found: every value it shows is in a file a reader can open without it.

---

## 2. What the feasibility test showed (evidence for the work list)

Cuprizone H1c (a study-side analysis: 12 tests × 4 measures × grey-matter
summaries, plus 11,808 ROI rows) was exported into source-lightbox's layout and
built with **no code change**. The export lived in the study's gitignored
`scratch/` and will not survive, so the mapping is recorded here:

| source-lightbox column / name | filled from (study table) |
|---|---|
| `hypothesis` | `test` + `__` + `level` (e.g. `change_group__p60_to_p120`) |
| `band` (the heatmap column axis) | `measure` (ReHo, fALFF, ReHo_zscore, fALFF_zscore, FC_*) |
| `dv` (facet) | `variable` (GM_all, GM_L, GM_R, FC_homotopic, …) |
| `spatial` (ROI table only) | `variable` (SIGMA region name) |
| `effect_size` | `d` (Cohen's d, **not** Hedges g) |
| `stat`, `p_value` | `t`, `p` (**uncorrected**, by the study's decision) |
| file `h1c_effect_size_summary.csv` | `summary_effects.csv` (named so the filename priority makes it the overview) |
| file `h1c_posthoc_roi.csv` | `roi_effects.csv` (priority 10, capped at 500 rows, full CSV linked) |
| `provenance.json` | a stand-in built from the study's run ledger — in the target design the producing package writes it (§4) |
| `contrasts:` in study.yaml | 12 entries with `label`, `group` (tier) and `role` (the study's pre-specified test `confirmatory`, the rest `exploratory`) |

**Worked:** the overview heatmap (test × measure, d per cell, ★ where p < 0.05)
shows every test *including nulls with their magnitude*, and its numbers match
the study's own tables (ReHo group change p60→p120 d = 1.30; control change
−1.46; p60 gap −1.19). Tier sections, the confirmatory badge, nulls listed in
place, sortable tables with the full CSV linked, and the provenance strip all
worked.

**Wrong — and items 1–4 are wrong for EEG galleries too:**

1. **The digest says "FDR q < 0.05"** when the table carries only an uncorrected
   `p`: `_sig_note` (`summarize.py:457`) falls back to FDR wording. A false
   statement of the multiple-comparison correction.
2. **Effect sizes are labelled "g" / "Hedges g"** whatever they are:
   `_EFFECT_COLS` (`summarize.py:35`) formats `effect_size` as `g=`, and the
   heatmap colour bar reads "Hedges g".
3. **Direction wording assumes two groups**: "▲/▼ = the first-listed group of
   each pair is higher" is shown for one-sample (within-group change) tests,
   where the arrow means increase/decrease.
4. **The digest drops magnitude for nulls and has no CIs**: a non-significant
   contrast reads "No significant effects" (`_null_item`, `summarize.py:1113`);
   CIs are rendered only for decoding tables (`ci_*`).
5. **Provenance fields are EEG-shaped**: the strip expects source-analytics'
   version, atlas, inverse method and source sampling (`_trim_provenance`,
   `manifest.py:25`); an MRI commit had to be put in the "source_analytics"
   version field.
6. **Every analysis lands in "Other"** without a source-analytics interpreter:
   grouping metadata comes from `source_analytics.core.analysis_meta()` via a
   subprocess (`_read_analysis_meta`, `builder.py:219`).
7. **No place for decision criteria**: an analysis that defines them (H1c writes
   a `verdict.json`: holds / does not, per criterion) has nowhere to show them.
8. Heatmap rows came out interleaved by window rather than in tier order.

Items 1–3 and 5 are also signs that the *information* was missing from the
files: nothing in the tables said the p was uncorrected, the effect was Cohen's
d, or the test was one-sample. The fix is in the output specification (§4) as
much as in the lightbox.

## 3. Where source-lightbox is EEG-specific today (what moves into the EEG profile)

| Place | EEG assumption |
|---|---|
| `render.py:34` `BAND_ORDER`, `summarize.py:93` `_GRAPH_BAND_ORDER` | frequency bands as the category axis |
| `render.py` `REGISTRY` renderers' `matches()` | source-analytics native column names (`hypothesis`, `band`, `spatial`, `dv`, `effect_size`, `stat`, `q_value`) |
| `render.py:39` `_SIG_PVAL_COLS`, `_is_sig` | significance precedence `significant → q → p_corrected → p_fdr → p_value`, threshold 0.05 fixed |
| `render.py:611` `_table_priority` | table roles inferred from filenames |
| `summarize.py` (`_EFFECT_COLS`, comparison/FCD/graph/NBS/cluster/ROI-posthoc builders, `_sig_note`) | g labels, band chips, FDR wording, EEG module types |
| `brain_mosaic.py`, `_brain_render_worker.py`, `circos.py`, `_circos_render_worker.py`, `_worker_atlas.py` | Allen atlas and source-analytics' viz, via a subprocess to its venv |
| `scanner.py` `LocalizationScanner`, `qc_meta.py`, `cli.py` (`localiz*` ×15) | the "inputs" side is source localization |
| `manifest.py:25` `_trim_provenance` | source-analytics provenance.json fields |
| `builder.py:219` `_read_analysis_meta` | analysis grouping from source-analytics |
| `config.py:18` `RETIRED_ANALYSES` | the retired vertex modules |
| `static/js/app.js` (2,128 lines: "band" ×57, "sensor" ×43, "localiz" ×40, `ACRONYMS`, Localization/Source-vs-Sensor nav, provenance labels) | EEG vocabulary hard-coded in the app |

## 4. The results output specification — owned by the analysis packages

A documented, versioned specification of **what an analysis package writes**,
so that any reader can use it. neurofaune and source-analytics produce it;
neuro-lightbox is one reader. It is deliberately boring: plain files, open
formats, everything described in the files themselves.

**Requirements**

- **Open formats only:** tables as CSV (or TSV), metadata as JSON, maps as NIfTI
  (MRI) — no pickles, no `.npz` as the only copy of a result, nothing that needs
  a particular package to read.
- **Self-describing:** every table has a column dictionary — a BIDS-style JSON
  sidecar beside it (`<table>.json`: per column, a description, units, levels),
  the convention BIDS already uses for tabular files, and close to neurofaune's
  existing BIDS-derivatives habits.
- **Complete:** every test that was run has its row — significant or not — with
  its effect and uncertainty. Tables are never truncated; a reader never needs
  the lightbox to see a row.
- **Explicit, not inferred:** the correction (`p_kind`), the effect measure, the
  test kind (direction semantics), units, and each table's role are written, not
  left to be guessed from column names or filenames.
- **Provenance included:** which package, version and commit produced each
  analysis; when; on what inputs; whether the run finished.
- **Versioned:** every `analysis.json` carries `spec_version`; changes follow
  semver (a reader written for 1.x reads every 1.y).
- **Workflow-neutral:** no field belongs to a particular workflow tool. A generic
  `references: [{label, value}]` list holds anything a study or tool wants
  attached (a pre-registration id, a finding id, a ticket); producers and readers
  treat it as opaque.

**Layout** (one folder per analysis, under whatever root the package uses):

```
<analysis>/
  analysis.json          what this analysis is (below)
  provenance.json        what produced it (below)
  tables/<name>.csv      results, one row per test / element
  tables/<name>.json     column dictionary for that table
  maps/…                 optional images (NIfTI for MRI), each listed in analysis.json
  figures/…              optional, never the only copy of a result
```

**Table columns** (a table carries the subset that applies; a reader reports a
missing field as missing, never guesses):

- identity: `contrast` (id), `category` (band / measure), `facet` (dv / metric /
  variable), `element` (ROI / cluster / edge / vertex)
- effect: `effect_size`, `effect_measure` (`d`, `g`, `beta`, `r`, `auc`, …),
  `ci_low`, `ci_high`, `effect_selected` (true where the effect was computed on
  units selected for significance — inflated)
- statistic: `stat`, `stat_name` (`t`, `F`, `z`, …), `df`
- significance: `p_value` with `p_kind` (`uncorrected`, `fdr`, `fwe`, `perm`),
  or explicit `q_value` / `p_corrected`
- design: `test_kind` (`two_group`, `one_sample`, `regression`, …), `group_a`,
  `group_b`, `n_a`, `n_b` (or `n`)
- descriptives: `mean_a`, `mean_b`; units in the column dictionary

**`analysis.json`:** `spec_version`, title, description, the analysis type, the
`role` (confirmatory / exploratory / descriptive / diagnostic — source-analytics'
hypotheses already carry one), the **correction statement** and threshold, the
effect measure, the design (groups, n per group), **decision criteria and their
outcome** where the analysis defines them (holds / does not, each criterion
pass/fail), each table's **role** (headline / detail / per-element) — replacing
filename conventions — the maps and figures it wrote, `retired`, and
`references`.

**`provenance.json`:** `tools: [{name, version, commit}]`,
`run: {id, start, end, status}`, `inputs`, `subjects: {n, groups}`, `caveats`.
source-analytics already writes a provenance.json (v0.8.2+) close to this;
neurofaune would write it from `neurofaune.provenance` — the same reader its
derivative `GeneratedBy` sidecars use.

**Where the specification lives** — an open decision (§8). Recommended: a small
standalone, versioned spec (a document, JSON Schemas, and an optional
conformance checker), which both packages cite and test against in their own
test suites, and which neither requires at runtime. The alternatives — writing
it into source-analytics' docs and adopting it in neurofaune, or keeping two
copies — either make one package the owner of the other's format or invite the
two copies to drift.

## 5. Target architecture (neuro-lightbox)

- **Package `neuro_lightbox`, CLI `neuro-lightbox`.** For a deprecation window:
  a `source-lightbox` console script (prints a one-line deprecation note) and a
  `source_lightbox` import shim (re-exports, `DeprecationWarning`). Existing
  `study.yaml` files keep working unchanged. The repository is
  `alexedmon1/neuro-lightbox`, with source-lightbox's history; source-lightbox
  stays frozen at its last commit, so scripts that run
  `uv run --project ~/sandbox/source-lightbox source-lightbox …` keep working
  until they are pointed here. Version continues: first neuro-lightbox release
  0.2.0.
- **Core (no domain vocabulary):** reading spec-conformant results trees (§4);
  the manifest; the static app; the renderer registry; the digest framework; the
  provenance strip; the "inputs/QC" section frame; `build` / `serve` / `info`;
  deploy.
- **Profile interface** — a Protocol/ABC, built-ins `eeg` and `mri`, third-party
  profiles discovered through the entry-point group `neuro_lightbox.profiles`.
  Selected by `profile:` in study.yaml; **absent means `eeg`**, so every existing
  config builds as today. Each built-in profile reads **its analysis package's
  output tree**: `eeg` reads source-analytics results trees (today's behaviour,
  including trees written before the spec), `mri` reads neurofaune's. Once a
  package writes the spec, its profile needs little more than vocabulary and
  domain renderers. A profile supplies:
  - `axes` — the category axis and its order (bands / measures), the element axis
    (ROI, vertex, voxel, cluster, edge), facet columns;
  - `column_map` — pre-spec native column names → the spec's (for older trees);
  - `renderers` — extra renderers registered ahead of the core ones
    (EEG: brain mosaics, circos; MRI: §6 Phase 4);
  - `digest_builders` — extra or overriding digest builders;
  - `input_scanners` — the inputs side (EEG: localization subjects/QC; MRI: link
    to neurofaune's preprocessing QC index);
  - `provenance_fields` — which provenance keys to show and their labels;
  - `analysis_meta` — grouping/domains (EEG: the source-analytics subprocess for
    pre-spec trees; otherwise `analysis.json`);
  - `vocabulary` — acronyms, glossary, nav labels; the app reads them from the
    manifest instead of hard-coding them.
- Heavy, domain-specific rendering stays **delegated by subprocess** to the
  domain package's own environment (EEG → source-analytics, as now; MRI →
  neurofaune, if atlas figures are added), so the gallery stays lightweight.
- **No DUET, no study-specific code** anywhere in neuro-lightbox.

## 6. The work, in phases

Each phase ends with its acceptance check; nothing moves to the next phase on a
failing one. Phases S and 0 can run in parallel.

### Phase S — the output specification (in the analysis packages)
- Write the specification (§4): document, JSON Schemas, conformance checker.
- **source-analytics:** close the gap from its current output (tables +
  provenance.json) — add `analysis.json`, column dictionaries, `p_kind`,
  `effect_measure`, `test_kind`; keep writing the existing columns for older
  readers.
- **neurofaune (Phase 4a in earlier drafts):** each analysis (TBSS, voxelwise,
  ROI extraction, covariance networks, connectomes, …) writes its own spec folder
  — tables, column dictionaries, `analysis.json`, `provenance.json`. The
  `tbss-reporting` branch's `tests.csv` / `clusters.csv` are the first candidates.
  neurofaune's older `reporting/` registry becomes a reader of the spec, or
  retires.
- **Accept:** each package's test suite validates its outputs against the
  schemas; and a **"no lightbox" test** — a plain pandas script that knows only
  the spec reads every table, its column meanings, the correction and the
  provenance of one source-analytics and one neurofaune analysis.

### Phase 0 — lightbox groundwork (no behaviour change)
- **Golden manifests.** Build galleries from fixture trees — an EEG fixture
  mirroring a real source-analytics tree, and an MRI fixture — and freeze their
  `manifest.json`. Every later phase diffs against these; an EEG gallery changes
  only where a change is intended.
- Find out who else uses source-lightbox (sets the deprecation window).
- **Done (2026-10-02).** `tests/test_golden.py` builds four galleries through
  the CLI and compares each with `tests/golden/<case>/`: the manifest (one table
  row per line, its exact bytes pinned by hash), the page, every output file
  (hashes for everything copied), the calls to the source-analytics workers, and
  the rendered figures (under the recording matplotlib / numpy / Pillow). Cases:
  `eeg` (FORGE treatment, with a stand-in source-analytics interpreter that
  serves v0.8.2's analysis metadata and answers the mosaic / circos workers),
  `eeg_no_sa` (the same tree with no interpreter), `eeg_legacy` (retired vertex
  modules, legacy column names, plugin provenance, two compared results trees)
  and `mri_h1c` (the §2 export; its golden build reproduces §2's defects, as it
  should until Phase 3). Together they reach all seven renderers and every
  digest builder. Both studies are unpublished and the repository is public, so
  the fixtures keep the trees' structure and replace every measured value with a
  synthetic one (`tests/fixtures/README.md`). `--update-golden` accepts an
  intended change; the diff of `tests/golden/` is its record.
- **Who uses source-lightbox (2026-10-02):** nobody outside the author's own
  work that can be found — 0 stars, forks and watchers, 0 page views in 14 days
  (30 clones, unattributable). Local users, all the author's: FORGE's
  `scripts/build_gallery.sh`, `scripts/build_gallery_split.sh` and
  `treatment/build_gallery_v2.sh` (run the CLI from `~/sandbox/source-lightbox`),
  the cuprizone feasibility export, the lab website's publishing notes, and
  source-analytics' README / CLAUDE.md / CHANGELOG. **The lab website reads
  gallery manifests** (`website/public/lib/scanner.php`: `title`,
  `stats.total_figures`, `stats.total_tables`, `stats.paradigm_count`,
  `sources`) — those keys are a contract to keep. So the deprecation window
  (§8, 2) can be short: the alias and shim cover a release or two.

### Phase 1 — rename (mechanical)
- `src/source_lightbox` → `src/neuro_lightbox`; pyproject name, console scripts
  (`neuro-lightbox`, alias `source-lightbox`), the import shim, README /
  DESIGN_NOTES / DEPLOY / FIGURE_INVENTORY, nginx/Apache examples.
- **Accept:** golden manifests byte-identical; tests pass under both names.
- **Done (2026-10-02).** Every golden build byte-identical. The suite passed
  twice: unchanged, still importing `source_lightbox` (through the shim), and
  after moving to `neuro_lightbox`. `tests/test_compat.py` keeps the old names
  honest: `source_lightbox.X` is the same module object as `neuro_lightbox.X`
  (so a monkeypatch through either reaches both), and `source-lightbox`,
  `neuro-lightbox` and `python -m source_lightbox` each build the `eeg_legacy`
  golden gallery, the old ones saying once on stderr that they are deprecated.
  `app.js`'s header comment still says source-lightbox: it is shipped in every
  gallery, and Phase 2 edits the file anyway.

### Phase 2 — profile interface; EEG specifics into `profiles/eeg`
- Move everything in §3 behind the profile: band orders, the source-analytics
  renderers and workers, localization scanning and QC meta, `analysis_meta`,
  `RETIRED_ANALYSES`, the provenance trimming, filename-based table priority,
  the EEG digest builders, and the app's vocabulary (served from the manifest).
- **Accept:** EEG golden manifests identical; a **core-purity test** fails if the
  core mentions bands, Allen, source-analytics, localization, DUET, or any study.

### Phase 3 — contract-correct core (improves EEG galleries too)
1. **Correction stated from the data, never defaulted.** Read from `p_kind` /
   `analysis.json`; an uncorrected p reads "uncorrected p < 0.05"; a pre-spec
   tree that does not say reads "correction not recorded". Replaces `_sig_note`'s
   FDR fallback (§2 item 1).
2. **Effect-size label from `effect_measure`** — d, g, β, r — in digest chips,
   heatmap colour bars and tables (item 2).
3. **Direction by `test_kind`**: two-group "A > B" with the group names;
   one-sample "increase / decrease"; regression "positive / negative" (item 3).
4. **Nulls with magnitude.** Every contrast in the digest shows its primary
   effect and CI, significant or not — "n.s.: d = 0.05 [−0.40, 0.51], uncorrected
   p = 0.83" instead of "No significant effects"; significant ones lead (item 4).
5. **CIs everywhere they exist**: digest text, and a CI-width cue (hatching or a
   companion panel) in heatmaps.
6. **Decision-criteria panel** from `analysis.json`: holds / does not, each
   criterion pass/fail, and any `references` — above the tabs (item 7).
7. **No significance-count headline.** Today's lead "31 significant effects
   across 7 of 12 comparisons" becomes: the headline table's (or confirmatory
   test's) effect, CI, p and correction first; counts after, labelled with their
   threshold.
8. **Selected effects flagged** (`effect_selected`) as inflated by selection.
9. **Order follows the config / `analysis.json`** — tiers, then contrast order —
   in digests, heatmap rows and tables (item 8).
10. **Absence visible.** An analysis declared but with no tables shows as "no
    result"; a provenance `run.status` of failed / incomplete shows on the page;
    the display cap says "showing 500 of 11,808" and links the full file.
11. **Grouping without a domain interpreter** — from `analysis.json` or config,
    never an "Other" dump (item 6).
12. **Generic provenance strip** (§4), "not recorded" when absent (item 5).
13. **Escape every name** that reaches HTML (region, contrast and measure names
    can contain `<` and `&`).
14. Units from the column dictionaries.
- Keep what works: tiers, role badges, gating notes, column-driven renderers,
  sortable tables, static build, deploy.
- **Accept:** contract tests on both fixtures — every contrast appears in the
  digest with effect, CI (where present), direction and the correction statement
  that matches its `p_kind`; the EEG golden diff lists only the intended changes,
  for the author to review.

### Phase 4 — MRI profile
- Reads neurofaune's spec folders (Phase S). Axes: category = measure
  (configured order, e.g. FA, MD, AD, RD, MK, AK, RK, KFA, FICVF, ODI, FISO;
  ReHo, fALFF, …); facets = variable / window.
- Renderers: test × measure effect heatmap with CI cue; **per-cohort
  consistency** (effect per cohort/batch, dot plot) where a design has cohorts;
  ROI effect table with atlas names; TBSS tests and cluster tables (voxels, mm³,
  peak, named regions); NBS components with signed edges; network distance
  against its permutation null.
- Inputs side: link neurofaune's preprocessing QC index (`qc/index.html`) as the
  MRI counterpart of EEG's localization QC.
- Later, optional: atlas figures (SIGMA ROI mosaics, skeleton montages),
  delegated by subprocess to neurofaune's environment.
- **Accept:** a neurofaune fixture (the TBSS read-out) and a study-orchestrator
  fixture (H1c, §2) build with the MRI profile, with none of §2's defects.

### Phase 5 — study adoption (each study's own side; cuprizone first)
- A study's own orchestration scripts (cuprizone's `h1_*` analyses are
  study-specific by design) write the **same spec folders** neurofaune writes —
  ideally through a small writer helper neurofaune provides — so their outputs
  are as readable by anyone as the packages' are. Whatever a study keeps in its
  own records (cuprizone keeps DUET findings and a run ledger) can go into the
  generic `references` and provenance fields; neither neuro-lightbox nor the
  spec knows about them.
- A `study.yaml` for the gallery; build into the study's report folder.

### Phase 6 — EEG regression and release
- Rebuild an existing EEG study gallery; review the diff against its golden
  manifest with the author (Phase 3 changes EEG digests on purpose — the
  correction wording, d/g labels, null magnitudes).
- Tag neuro-lightbox 0.2.0; update references in source-analytics' docs.

## 7. Testing

- Spec conformance tests in each producing package, and the "no lightbox" read
  test (Phase S).
- Golden manifests per fixture (Phase 0) — the regression net for EEG.
- Core-purity test (Phase 2).
- Contract tests (Phase 3): per contrast, effect + CI + direction + a correction
  statement consistent with `p_kind`; nulls present with magnitude.
- The neurofaune and H1c fixtures as the MRI acceptance tests (Phase 4).
- Existing suites (`tests/test_*.py`) keep passing under both package names.

## 8. Open decisions (author)

1. **Where the output specification lives**: a small standalone spec
   (recommended), source-analytics' docs adopted by neurofaune, or two copies.
2. Other users of source-lightbox, and so the length of the deprecation window.
   *Phase 0 found none outside the author's own scripts (§6, Phase 0); a short
   window is enough.*
3. Profile selection: explicit `profile:` with `eeg` as the default
   (recommended) or auto-detection from the tree.
4. Whether the MRI profile is built in (recommended for now) or shipped from
   neurofaune through the entry point.
5. Whether studies commit the built HTML or rebuild it from committed tables (the
   preprocessing QC index does the latter).
6. The reporting contract (magnitude + direction + extent + location + nulls,
   currently written in the cuprizone study's `analyses/REPORTING.md`): make it
   part of the output specification, so producers meet it and any reader —
   neuro-lightbox's contract tests included — can check it.

## 9. Related, outside this plan

- neurofaune branch `tbss-reporting` (`67c60fd`, validated against the cuprizone
  H1h output; HTML escaping still to fix; not merged, no pin bump): the first
  neurofaune analysis to produce test-level tables of the kind §4 specifies.
- neurofaune's own `reporting/` registry + `index.html` (older; headline is a
  significance count) — becomes a reader of the spec, or retires.
