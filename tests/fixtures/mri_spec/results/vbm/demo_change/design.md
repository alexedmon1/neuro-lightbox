# What this randomise design tests

Does GM change within treated animals? (synthetic)

**12 rows** (treated: 12), one per observation; row *i* of `design.mat` is the *i*-th subject listed in order in `design.json` (`rows.ids`).

**Each row's observation:** each treated animal's synthetic GM change, later minus earlier (`all_GM_change.nii.gz`).

## Design matrix — `design.mat`, 12 × 1

| # | Column | What it codes |
|---|---|---|
| 1 | `intercept` | 1 for every treated animal: the mean change *(intercept)* |

## Contrasts — `design.con`

Each is a t-test; randomise's `tstat<i>` / `*_tstat<i>` maps are contrast *i*. A positive statistic means what the contrast says.

| # | Name | Tests | Kind | Vector |
|---|---|---|---|---|
| 1 | `increase` | mean GM change > 0 in treated animals | one_sample | `[1]` |
| 2 | `decrease` | mean GM change < 0 in treated animals | one_sample | `[-1]` |

_Schema `neurofaune.design/1`; written by neurofaune 0.11.0a0 on 2026-10-06T00:00:00+00:00._
