# What this randomise design tests

Do treated animals differ from controls on the skeleton? (synthetic)

**22 rows** (treated: 12; control: 10), one per observation; row *i* of `design.mat` is the *i*-th subject listed in order in `design.json` (`rows.ids`).

**Each row's observation:** each animal's synthetic value on the TBSS skeleton (`all_<measure>_skeletonised.nii.gz`).

## Design matrix — `design.mat`, 22 × 2

| # | Column | What it codes |
|---|---|---|
| 1 | `treated` | 1 if the animal is in the treated group, else 0 *(group)* |
| 2 | `control` | 1 if the animal is in the control group, else 0 *(group)* |

## Contrasts — `design.con`

Each is a t-test; randomise's `tstat<i>` / `*_tstat<i>` maps are contrast *i*. A positive statistic means what the contrast says.

| # | Name | Tests | Kind | Vector |
|---|---|---|---|---|
| 1 | `treated>control` | treated mean > control mean | two_group (treated vs control) | `[1, -1]` |
| 2 | `control>treated` | control mean > treated mean | two_group (control vs treated) | `[-1, 1]` |

_Schema `neurofaune.design/1`; written by neurofaune 0.11.0a0 on 2026-10-06T00:00:00+00:00._
