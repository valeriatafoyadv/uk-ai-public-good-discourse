#!/usr/bin/env python3
"""Phase 6D -- NVivo plan query 2: agency x genre (SO3, Fairclough 2003).

Reads the AGENCY records in coding/round1/*.jsonl (skipping any record that
carries an "error" field -- Round 1 coding is partial while the Ollama Cloud
quota is being drained in bursts, see coding/round1/run_meta.json), maps the
Spanish `form` values emitted by the active prompt run
(agente_explicito / pasiva_sin_agente / nominalizacion) to the English labels
used throughout this project (explicit_agent / agentless_passive /
nominalisation), and cross-tabulates instance counts against genre (from
data/manifest.csv).

Output: analysis/queries/agency_by_genre.csv -- one row per genre, one column
per form. A leading "# STATUS: PARTIAL ..." comment line is written whenever
the latest Round 1 run (per run_meta.json) has not completed, so the file is
never mistaken for corpus-wide counts. scripts/07b_queries.py reads this
comment line to decide whether to show the same partial-coverage note next to
the chart it renders from this CSV.

Idempotent: safe to re-run after every Round 1 batch completes further docs;
it always recomputes from whatever is currently in coding/round1/*.jsonl.

Usage:
    .venv/bin/python scripts/11_agency_query.py
"""
import csv
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "data", "manifest.csv")
OUT_CSV = os.path.join(ROOT, "analysis", "queries", "agency_by_genre.csv")

GENRES = ["STRAT", "MOU", "PRGOV", "PRCO", "BLOG", "WMS", "REG"]
FORMS = ["explicit_agent", "agentless_passive", "nominalisation"]
FORM_MAP = {
    "agente_explicito": "explicit_agent",
    "pasiva_sin_agente": "agentless_passive",
    "nominalizacion": "nominalisation",
}

SKIP_FILES = {"doc_profiles.jsonl", "definitional_instances.jsonl"}


def load_manifest():
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        return {r["doc_id"]: r for r in csv.DictReader(f)}


def load_agency_records():
    """Return (instances, n_pairs_attempted, n_pairs_ok) for question AGENCY.

    instances: list of {"doc_id", "form"} for every successful, applicable
    AGENCY record whose form value maps to one of the three known labels.
    n_pairs_attempted / n_pairs_ok count unit-question calls (error or not),
    mirroring the accounting in coding/round1/run_meta.json.
    """
    instances = []
    n_attempted = 0
    n_ok = 0
    unmapped = set()
    for path in sorted(glob.glob(os.path.join(ROOT, "coding/round1/*.jsonl"))):
        base = os.path.basename(path)
        if base in SKIP_FILES or base.startswith("CONTEXT_"):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get("question") != "AGENCY":
                    continue
                n_attempted += 1
                if "error" in d:
                    continue
                n_ok += 1
                if not d.get("applies") or not d.get("instance_data"):
                    continue
                inst = d["instance_data"]
                obj = json.loads(inst) if isinstance(inst, str) else inst
                form_es = obj.get("form")
                form_en = FORM_MAP.get(form_es)
                if form_en is None:
                    unmapped.add(form_es)
                    continue
                instances.append({"doc_id": d["doc_id"], "form": form_en})
    if unmapped:
        print(f"WARNING: unmapped AGENCY form values, skipped: {sorted(unmapped)}")
    return instances, n_attempted, n_ok


def latest_run_pct():
    """Same signal 06_consolidate.py uses -- keeps the PARTIAL threshold
    consistent across every Phase 6 output."""
    meta_path = os.path.join(ROOT, "coding/round1/run_meta.json")
    if not os.path.exists(meta_path):
        return None
    meta = json.load(open(meta_path, encoding="utf-8"))
    runs = meta.get("runs", [])
    if not runs:
        return None
    return runs[-1].get("pct_calls_succeeded")


def main():
    manifest = load_manifest()
    instances, n_attempted, n_ok = load_agency_records()

    total_docs = len({d for d, r in manifest.items() if r.get("is_context") != "True"})
    docs_with_agency = len({i["doc_id"] for i in instances})
    pct_calls = latest_run_pct()
    is_partial = pct_calls is None or pct_calls < 99.5

    matrix = {g: {f: 0 for f in FORMS} for g in GENRES}
    for inst in instances:
        genre = manifest.get(inst["doc_id"], {}).get("genre")
        if genre in matrix:
            matrix[genre][inst["form"]] += 1

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        if is_partial:
            pct_txt = f"{pct_calls:.1f}%" if pct_calls is not None else "unknown"
            f.write(
                "# STATUS: PARTIAL -- regenerate after Round 1 completes. "
                f"Coverage: {docs_with_agency}/{total_docs} documents contributed at least one "
                f"successful AGENCY instance ({len(instances)} instances total, from "
                f"{n_ok}/{n_attempted} AGENCY unit-question pairs attempted so far; latest Round 1 "
                f"run at {pct_txt} of all calls -- see coding/round1/run_meta.json). Counts below "
                "are NOT corpus-wide; re-run scripts/11_agency_query.py once Round 1 completes.\n"
            )
        writer = csv.writer(f)
        writer.writerow(["genre"] + FORMS)
        for g in GENRES:
            writer.writerow([g] + [matrix[g][form] for form in FORMS])

    print(f"AGENCY x genre: {len(instances)} instances from {docs_with_agency}/{total_docs} documents "
          f"({n_ok}/{n_attempted} AGENCY unit-question pairs succeeded so far)")
    if is_partial:
        pct_txt = f"{pct_calls:.1f}%" if pct_calls is not None else "unknown"
        print(f"STATUS: PARTIAL -- latest Round 1 run at {pct_txt} of calls. "
              "Re-run after Round 1 completes.")
    else:
        print("STATUS: COMPLETE")
    print(f"Wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
