#!/usr/bin/env python
"""Phase 3 - Model evaluation (Ollama Cloud).

Runs the 11 questions from coding/prompts/prompts_v1.yaml over a stratified
sample of 6 units, for each candidate model, and computes metrics (verbatim
fidelity / JSON validity / reasonable applies=false rate) to decide the
winning model for Phase 4.

Outputs: coding/model_eval/results.csv (one row per unit x question x model)
         coding/model_eval/decision.md (summary and decision)
"""
import csv
import json
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OLLAMA_URL = "http://localhost:11434/api/generate"
TIMEOUT = 180
RETRIES = 2

MODELS = [
    "gpt-oss:120b-cloud",
    "glm-5.3:cloud",
    "kimi-k3:cloud",
    "deepseek-v4-flash:cloud",
]

# Stratified sample (see rationale in decision.md)
SAMPLE_UNIT_IDS = [
    "2025-02-10_STRAT_GDS_AIPlaybookUKGovernment::s130",   # long STRAT
    "2025-07-21_MOU_OpenAI_AIOpportunities::s02",           # MOU
    "2026-01-27_PRCO_Anthropic_GOVUKPartnership::s01",      # PRCO
    "2026-01-20_BLOG_GDS_OurRoadmapLaunch::s03",            # BLOG
    "2025-12-10_PRCO_DeepMind_StrengtheningPartnership::s06",  # retrieval=semantic
    "2026-01-19_WMS_DSIT_RoadmapMinisterialStatement::full",   # full_short_doc (WMS)
]


def load_manifest():
    manifest = {}
    with open(os.path.join(ROOT, "data/manifest.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            manifest[row["doc_id"]] = row
    return manifest


def doc_title(doc_id):
    path = os.path.join(ROOT, "data/text", doc_id + ".json")
    if not os.path.exists(path):
        # strip CONTEXT_ prefix if present
        return doc_id
    d = json.load(open(path, encoding="utf-8"))
    for b in d["blocks"]:
        if b["structural_position"] == "title":
            return b["text"].strip()
    return doc_id


def build_doc_context(doc_id, manifest):
    row = manifest.get(doc_id, {})
    title = doc_title(doc_id)
    return f"{title} | {row.get('date','?')} | {row.get('genre','?')} | {row.get('speaker','?')} | {row.get('family','None')}"


def load_units():
    units = {}
    with open(os.path.join(ROOT, "coding/units.jsonl"), encoding="utf-8") as f:
        for line in f:
            u = json.loads(line)
            units[u["unit_id"]] = u
    return units


def load_prompts():
    with open(os.path.join(ROOT, "coding/prompts/prompts_v1.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def call_ollama(model, prompt, retries=RETRIES):
    last_err = None
    for attempt in range(retries + 1):
        try:
            t0 = time.time()
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0},
                },
                timeout=TIMEOUT,
            )
            elapsed = time.time() - t0
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                last_err = data["error"]
                continue
            return data.get("response", ""), elapsed, None
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            time.sleep(1)
    return "", 0.0, last_err


def verify_quotes(passage, parsed):
    """Return (n_quotes, n_verbatim_ok)."""
    n, ok = 0, 0
    instances = parsed.get("instances", []) if isinstance(parsed, dict) else []
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        q = inst.get("verbatim_quote")
        if q:
            n += 1
            if q in passage:
                ok += 1
    return n, ok


def run_one(model, qname, qdef, common_header, unit, doc_context):
    passage = unit["text"]
    header = common_header.replace("{doc_context}", doc_context).replace("{passage}", passage)
    full_prompt = header + "\n" + qdef["prompt"]
    raw, elapsed, err = call_ollama(model, full_prompt)
    record = {
        "model": model,
        "unit_id": unit["unit_id"],
        "question": qname,
        "passage_len": len(passage),
        "elapsed_s": round(elapsed, 2),
        "raw_response": raw,
        "error": err,
        "json_valid": False,
        "applies": None,
        "n_quotes": 0,
        "n_quotes_verbatim_ok": 0,
    }
    if err:
        return record
    try:
        parsed = json.loads(raw)
        record["json_valid"] = True
        record["applies"] = parsed.get("applies") if isinstance(parsed, dict) else None
        n, ok = verify_quotes(passage, parsed)
        record["n_quotes"] = n
        record["n_quotes_verbatim_ok"] = ok
    except Exception as e:  # noqa: BLE001
        record["error"] = f"json_parse_error: {e}"
    return record


def main():
    manifest = load_manifest()
    units = load_units()
    prompts = load_prompts()
    common_header = prompts["common_header"]
    questions = prompts["questions"]

    missing = [u for u in SAMPLE_UNIT_IDS if u not in units]
    if missing:
        print("WARNING missing sample units:", missing, file=sys.stderr)

    sample_units = [units[u] for u in SAMPLE_UNIT_IDS if u in units]
    doc_contexts = {u["doc_id"]: build_doc_context(u["doc_id"], manifest) for u in sample_units}

    tasks = []
    for model in MODELS:
        for unit in sample_units:
            for qname, qdef in questions.items():
                tasks.append((model, qname, qdef, unit))

    print(f"Total calls: {len(tasks)} ({len(MODELS)} models x {len(sample_units)} units x {len(questions)} questions)")

    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {
            ex.submit(run_one, model, qname, qdef, common_header, unit, doc_contexts[unit["doc_id"]]): (model, unit["unit_id"], qname)
            for (model, qname, qdef, unit) in tasks
        }
        done_n = 0
        for fut in as_completed(futs):
            rec = fut.result()
            results.append(rec)
            done_n += 1
            if done_n % 20 == 0:
                print(f"  {done_n}/{len(tasks)} done")

    out_csv = os.path.join(ROOT, "coding/model_eval/results.csv")
    fieldnames = ["model", "unit_id", "question", "passage_len", "elapsed_s", "json_valid",
                  "applies", "n_quotes", "n_quotes_verbatim_ok", "error", "raw_response"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k) for k in fieldnames})

    print(f"Wrote {out_csv} ({len(results)} rows)")

    # ---- Metrics per model ----
    from collections import defaultdict
    agg = defaultdict(lambda: {"n": 0, "json_valid": 0, "n_quotes": 0, "n_quotes_ok": 0,
                                "applies_false": 0, "applies_true": 0, "errors": 0})
    short_passage_threshold = 700
    short_applies_false = defaultdict(int)
    short_total = defaultdict(int)

    for r in results:
        m = r["model"]
        a = agg[m]
        a["n"] += 1
        if r["json_valid"]:
            a["json_valid"] += 1
        if r["error"]:
            a["errors"] += 1
        a["n_quotes"] += r["n_quotes"]
        a["n_quotes_ok"] += r["n_quotes_verbatim_ok"]
        if r["applies"] is True:
            a["applies_true"] += 1
        elif r["applies"] is False:
            a["applies_false"] += 1
        if r["passage_len"] < short_passage_threshold:
            short_total[m] += 1
            if r["applies"] is False:
                short_applies_false[m] += 1

    metrics_path = os.path.join(ROOT, "coding/model_eval/decision.md")
    lines = []
    lines.append("# Phase 3 -- Model evaluation (Ollama Cloud)\n")
    lines.append(f"Run date: {time.strftime('%Y-%m-%d')}\n")
    lines.append("\n## Candidates tested\n")
    lines.append(
        "The 4 model names suggested in the original plan "
        "(`deepseek-v3.1:671b-cloud`, `kimi-k2:1t-cloud`, `qwen3-coder:480b-cloud`, "
        "`glm-4.6:cloud`) no longer exist in the Ollama Cloud catalogue current as "
        f"of the run date ({time.strftime('%Y-%m-%d')}) -- `ollama pull` returned "
        "`pull model manifest: file does not exist` for all 4. The current catalogue "
        "was resolved against `ollama.com/search?c=cloud` and each placeholder was "
        "substituted with the current generation of the same provider/family:\n\n"
        "| Original placeholder | Current substitute tested |\n"
        "|---|---|\n"
        "| `glm-4.6:cloud` | `glm-5.3:cloud` |\n"
        "| `kimi-k2:1t-cloud` | `kimi-k3:cloud` |\n"
        "| `deepseek-v3.1:671b-cloud` | `deepseek-v4-flash:cloud` |\n"
        "| `qwen3-coder:480b-cloud` | not available (`qwen3.5:*-cloud` pull failed; omitted) |\n\n"
        "`gpt-oss:120b-cloud` (already-tested baseline) is retained as a candidate.\n"
        "All 4 evaluated candidates were verified with a short `/api/generate` call "
        "before the full run.\n"
    )

    lines.append("\n## Metrics per model (6 units x 11 questions = 66 calls/model)\n")
    lines.append("| Model | % valid JSON | % verbatim fidelity (quotes OK / total quotes) | applies=true | applies=false | errors | mean time (s) |\n")
    lines.append("|---|---|---|---|---|---|---|\n")

    summary_rows = []
    for m in MODELS:
        a = agg[m]
        pct_json = 100 * a["json_valid"] / a["n"] if a["n"] else 0
        pct_fid = 100 * a["n_quotes_ok"] / a["n_quotes"] if a["n_quotes"] else float("nan")
        avg_time = sum(r["elapsed_s"] for r in results if r["model"] == m) / a["n"] if a["n"] else 0
        summary_rows.append((m, pct_json, pct_fid, a["applies_true"], a["applies_false"], a["errors"], avg_time))
        lines.append(
            f"| {m} | {pct_json:.1f}% | {pct_fid:.1f}% ({a['n_quotes_ok']}/{a['n_quotes']}) | "
            f"{a['applies_true']} | {a['applies_false']} | {a['errors']} | {avg_time:.1f} |\n"
        )

    lines.append("\n## Reasonable applies=false on short passages (<700 characters)\n")
    lines.append("| Model | applies=false / calls on short passages |\n|---|---|\n")
    for m in MODELS:
        lines.append(f"| {m} | {short_applies_false[m]}/{short_total[m]} |\n")

    # Decision rule: verbatim fidelity wins; ties broken by JSON validity
    ranked = sorted(
        summary_rows,
        key=lambda row: (
            -1 if row[2] != row[2] else -row[2],  # nan pushed last (fidelity desc)
            -row[1],  # json valid desc
        ),
    )
    winner = ranked[0]
    lines.append("\n## Decision\n")
    lines.append(
        f"**Winning model: `{winner[0]}`** (verbatim fidelity {winner[2]:.1f}%, "
        f"valid JSON {winner[1]:.1f}%). Rule applied: verbatim fidelity wins "
        "(predefined decision criterion); ties are broken by % of valid JSON. "
        f"Provider: Ollama Cloud. Decision date: {time.strftime('%Y-%m-%d')}. "
        "This text can be cited almost verbatim in the methods chapter.\n"
    )
    lines.append(
        "\nScope note: agreement with the author on the sample (Phase 3, item 4 "
        "of the PLAN) is still pending -- this report only covers the automatic "
        "metrics (valid JSON, verbatim fidelity, reasonable applies=false). Human "
        "adjudication happens in the 15-20% validation of Phase 4.\n"
    )

    with open(metrics_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"Wrote {metrics_path}")
    print("WINNER:", winner[0])


if __name__ == "__main__":
    main()
