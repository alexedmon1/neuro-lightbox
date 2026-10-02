"""Throwaway feasibility export: H1c (h1_function_trajectory) -> source-lightbox layout.
Scratch only (gitignored). Maps study columns onto source-lightbox's native schema
and keeps every original column so the Tables tab shows them."""
import json
from pathlib import Path
import pandas as pd

SRC = Path("/mnt/arborea/cuprizone/analyses/results/h1/function")
OUT = Path(__file__).parent / "results" / "tables" / "rsfmri" / "h1c_function_trajectory"
OUT.mkdir(parents=True, exist_ok=True)

def native(df, spatial):
    d = df.copy()
    d.insert(0, "hypothesis", d["test"] + "__" + d["level"])
    d["band"] = d["measure"]            # the column axis of its heatmaps
    d["effect_size"] = d["d"]
    d["stat"] = d["t"]
    d["p_value"] = d["p"]
    if spatial:
        d["spatial"] = d["variable"]
    else:
        d["dv"] = d["variable"]          # facet: GM_all / GM_L / GM_R / ...
    return d

native(pd.read_csv(SRC / "summary_effects.csv"), False).to_csv(OUT / "h1c_effect_size_summary.csv", index=False)
native(pd.read_csv(SRC / "roi_effects.csv"), True).to_csv(OUT / "h1c_posthoc_roi.csv", index=False)

# provenance.json from the study ledger's latest completed run of the script
runs = [json.loads(l) for l in open("/mnt/arborea/cuprizone/provenance.jsonl")]
start = [r for r in runs if r.get("script") == "analyses/code/h1_function_trajectory.py" and r["event"] == "start"][-1]
end = [r for r in runs if r.get("run_id") == start["run_id"] and r["event"] == "end"][-1]
(OUT / "provenance.json").write_text(json.dumps({
    "written": end["time"],
    "source_analytics": {"version": f"study {start['study_commit'][:7]}; neurofaune {start['neurofaune']['commit'][:7]}"},
    "subjects": {"n": 34, "groups": {"control": 10, "cuprizone": 24}},
    "localization": {"description": "rs-fMRI, SIGMA grey-matter ROIs (run " + start["run_id"] + ")"},
}, indent=1))
print("exported:", sorted(p.name for p in OUT.iterdir()))
