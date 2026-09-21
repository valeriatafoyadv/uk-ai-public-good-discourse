#!/usr/bin/env python
"""Phase 4 -- Round 1 coding (LLM).

Runs the 11 questions from coding/prompts/prompts_v1.yaml over the 91 units in
coding/units.jsonl, and DOC_PROFILE over the full text of each of the 66
documents. Uses the winning model from Phase 3 (coding/model_eval/decision.md).

Usage:
    .venv/bin/python scripts/05_code.py                  # full run
    .venv/bin/python scripts/05_code.py --doc <doc_id>    # single document only
    .venv/bin/python scripts/05_code.py --questions core  # 7 core questions only
    .venv/bin/python scripts/05_code.py --model <name>    # force a model

Outputs:
    coding/round1/<doc_id>.jsonl              -- one record per question x instance
    coding/round1/doc_profiles.jsonl           -- one DOC_PROFILE record per doc
    coding/round1/definitional_instances.jsonl -- applies=true DEFINITIONAL, chronological order
    coding/round1/run_meta.json                -- run metadata
    coding/validation/sample_for_author.csv    -- 15-20% sample for double coding
      (only regenerated on a full run, not with --doc)
"""
import argparse
import csv
import json
import os
import random
import re
import sys
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLLAMA_URL = "http://localhost:11434/api/generate"
TIMEOUT = 180
RETRIES = 2
CONCURRENCY = 4
PROMPT_VERSION = 1
MAX_DOC_CHARS = 12000
# Safety cap for pathologically oversized units (segmentation artifacts, e.g. a
# heading that swallowed most of a document). Genuine long sections (~7-19k
# chars) are unaffected; this only clips true outliers (e.g. a 180k-char unit).
MAX_UNIT_CHARS = 20000

CORE_QUESTIONS = [
    "BENEFICIARY", "MECHANISM", "SAFEGUARD", "RESPONSIBILITY",
    "PROJECTED_FUTURE", "ACTANTS", "NATURALISED_ORDER",
]

CORRECTIVE_SUFFIX = (
    "\n\nIMPORTANT CORRECTION: at least one \"verbatim_quote\" in your previous "
    "answer was NOT an exact substring of the passage above. Re-read the passage "
    "and copy each verbatim_quote EXACTLY, character for character, from the "
    "passage text. Return the corrected JSON now, same schema."
)


def default_model():
    """Read the winning model from coding/model_eval/decision.md."""
    path = os.path.join(ROOT, "coding/model_eval/decision.md")
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read()
        m = re.search(r"Winning model:\s*`([^`]+)`", text)
        if m:
            return m.group(1)
    return "gpt-oss:120b-cloud"


def load_manifest():
    manifest = {}
    with open(os.path.join(ROOT, "data/manifest.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            manifest[row["doc_id"]] = row
    return manifest


def load_doc_json(doc_id):
    path = os.path.join(ROOT, "data/text", doc_id + ".json")
    return json.load(open(path, encoding="utf-8"))


def doc_title(doc_id, doc_json_cache):
    d = doc_json_cache[doc_id]
    for b in d["blocks"]:
        if b["structural_position"] == "title":
            return b["text"].strip()
    return doc_id


def full_doc_text(doc_id, doc_json_cache, max_chars=MAX_DOC_CHARS):
    d = doc_json_cache[doc_id]
    parts = []
    for b in d["blocks"]:
        parts.append(b["text"])
    text = "\n".join(parts)
    return text[:max_chars]


def build_doc_context(doc_id, manifest, doc_json_cache):
    row = manifest.get(doc_id, {})
    title = doc_title(doc_id, doc_json_cache)
    return f"{title} | {row.get('date','?')} | {row.get('genre','?')} | {row.get('speaker','?')} | {row.get('family','None')}"


def load_units():
    units = []
    with open(os.path.join(ROOT, "coding/units.jsonl"), encoding="utf-8") as f:
        for line in f:
            units.append(json.loads(line))
    return units


def load_prompts():
    with open(os.path.join(ROOT, "coding/prompts/prompts_v1.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def strip_json_fences(raw):
    """Some cloud models (e.g. kimi-k3) wrap JSON in ```json ... ``` fences even
    with format=json requested. Strip those before parsing."""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n", "", s)
        s = re.sub(r"\n?```\s*$", "", s)
    return s.strip()


def parse_json_response(raw):
    """Parse a model JSON response, tolerating markdown code fences and stray
    text around the JSON object. Raises the original json error if all attempts fail."""
    s = strip_json_fences(raw)
    try:
        return json.loads(s)
    except Exception as e:  # noqa: BLE001
        i, j = s.find("{"), s.rfind("}")
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except Exception:
                pass
        raise e


def call_ollama(model, prompt, retries=RETRIES):
    last_err = None
    for attempt in range(retries + 1):
        try:
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
            if resp.status_code == 429:
                # Ollama Cloud rate limit / session usage quota. A hard
                # account-level quota won't clear with a short backoff, but a
                # transient burst limit might -- back off longer than for
                # ordinary errors, then give up (retrying a hard quota just
                # wastes remaining budget once it clears).
                last_err = f"429 {resp.text.strip()[:300]}"
                time.sleep(5 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                last_err = data["error"]
                continue
            return data.get("response", ""), None
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            time.sleep(1)
    return "", last_err


def summarize_instance(inst):
    """Compact human-readable summary of one instance dict, minus verbatim_quote."""
    parts = []
    for k, v in inst.items():
        if k in ("verbatim_quote",):
            continue
        parts.append(f"{k}={v}")
    return "; ".join(parts)


def code_unit_question(model, run_id, unit, qname, qdef, header, passage):
    full_prompt = header + "\n" + qdef["prompt"]
    raw, err = call_ollama(model, full_prompt)
    timestamp = datetime.now(timezone.utc).isoformat()
    base = {
        "doc_id": unit["doc_id"],
        "unit_id": unit["unit_id"],
        "heading": unit.get("heading"),
        "question": qname,
        "so_tags": qdef.get("so_tags", []),
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "run_id": run_id,
        "timestamp": timestamp,
    }
    if err:
        return [dict(base, applies=None, error=err, raw_response=raw)]

    try:
        parsed = parse_json_response(raw)
    except Exception as e:  # noqa: BLE001
        return [dict(base, applies=None, error=f"json_parse_error: {e}", raw_response=raw)]

    applies = parsed.get("applies") if isinstance(parsed, dict) else None
    confidence = parsed.get("confidence") if isinstance(parsed, dict) else None
    instances = parsed.get("instances", []) if isinstance(parsed, dict) else []

    if not applies or not instances:
        return [dict(base, applies=bool(applies), confidence=confidence,
                      answer_summary=None, verbatim_quote=None, quote_verified=None,
                      instance_data=None)]

    # check verbatim quotes; retry whole call once if any fail
    def check(insts):
        return [(inst.get("verbatim_quote") or "") in passage for inst in insts]

    oks = check(instances)
    if not all(oks):
        raw2, err2 = call_ollama(model, full_prompt + CORRECTIVE_SUFFIX)
        if not err2:
            try:
                parsed2 = parse_json_response(raw2)
                instances2 = parsed2.get("instances", []) if isinstance(parsed2, dict) else []
                if instances2:
                    instances = instances2
                    applies = parsed2.get("applies", applies)
                    confidence = parsed2.get("confidence", confidence)
                    oks = check(instances)
            except Exception:  # noqa: BLE001
                pass

    records = []
    for inst, ok in zip(instances, oks):
        records.append(dict(
            base,
            applies=True,
            confidence=confidence,
            answer_summary=summarize_instance(inst),
            verbatim_quote=inst.get("verbatim_quote"),
            quote_verified=ok,
            instance_data=json.dumps(inst, ensure_ascii=False),
        ))
    return records


def code_doc_profile(model, run_id, doc_id, header):
    timestamp = datetime.now(timezone.utc).isoformat()
    prompt = header + "\n" + DOC_PROFILE_PROMPT
    raw, err = call_ollama(model, prompt)
    base = {
        "doc_id": doc_id, "model": model, "prompt_version": PROMPT_VERSION,
        "run_id": run_id, "timestamp": timestamp,
    }
    if err:
        return dict(base, error=err, raw_response=raw)
    try:
        parsed = parse_json_response(raw)
        return dict(base, error=None, **parsed)
    except Exception as e:  # noqa: BLE001
        return dict(base, error=f"json_parse_error: {e}", raw_response=raw)


def stratified_sample(units, manifest, target_n=10, seed=42):
    rng = random.Random(seed)
    by_genre = defaultdict(list)
    for u in units:
        genre = manifest[u["doc_id"]]["genre"]
        by_genre[genre].append(u)

    total = len(units)
    quotas = {}
    for genre, us in by_genre.items():
        quotas[genre] = max(1, round(len(us) / total * target_n))

    # adjust to hit target_n exactly, trimming/adding from largest groups
    diff = sum(quotas.values()) - target_n
    genres_by_size = sorted(by_genre, key=lambda g: -len(by_genre[g]))
    i = 0
    while diff > 0:
        g = genres_by_size[i % len(genres_by_size)]
        if quotas[g] > 1:
            quotas[g] -= 1
            diff -= 1
        i += 1
        if i > 100:
            break
    i = 0
    while diff < 0:
        g = genres_by_size[i % len(genres_by_size)]
        if quotas[g] < len(by_genre[g]):
            quotas[g] += 1
            diff += 1
        i += 1
        if i > 100:
            break

    sample = []
    for genre, us in by_genre.items():
        # prefer family diversity: shuffle deterministically, then sort by family
        # so consecutive picks favor different families
        us_sorted = sorted(us, key=lambda u: (manifest[u["doc_id"]]["family"], u["unit_id"]))
        rng.shuffle(us_sorted)
        seen_families = set()
        prioritized = []
        rest = []
        for u in us_sorted:
            fam = manifest[u["doc_id"]]["family"]
            if fam not in seen_families:
                prioritized.append(u)
                seen_families.add(fam)
            else:
                rest.append(u)
        ordered = prioritized + rest
        sample.extend(ordered[:quotas[genre]])
    return sample


def write_validation_sample(units, manifest, doc_json_cache, results_by_unit_question):
    path = os.path.join(ROOT, "coding/validation/sample_for_author.csv")
    sample = stratified_sample(units, manifest, target_n=10)
    sample_ids = {u["unit_id"] for u in sample}

    fieldnames = ["unit_id", "doc_id", "genre", "family", "heading", "text"]
    for q in CORE_QUESTIONS:
        fieldnames.append(f"AUTHOR_{q}")
        fieldnames.append(f"LLM_{q}")

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for u in sample:
            row = {
                "unit_id": u["unit_id"],
                "doc_id": u["doc_id"],
                "genre": manifest[u["doc_id"]]["genre"],
                "family": manifest[u["doc_id"]]["family"],
                "heading": u.get("heading"),
                "text": u["text"][:1200],
            }
            for q in CORE_QUESTIONS:
                row[f"AUTHOR_{q}"] = ""
                recs = results_by_unit_question.get((u["unit_id"], q), [])
                if not recs:
                    summary = "n/a"
                elif recs[0].get("applies") is False or recs[0].get("applies") is None:
                    summary = "does not apply" if recs[0].get("applies") is False else f"ERROR: {recs[0].get('error')}"
                else:
                    summary = " || ".join(r.get("answer_summary", "") or "" for r in recs)
                row[f"LLM_{q}"] = summary
            w.writerow(row)
    print(f"Wrote {path} ({len(sample)} units, ~{100*len(sample)/len(units):.0f}% of {len(units)})")
    return sample_ids


DOC_PROFILE_PROMPT = None  # set in main() from yaml


def main():
    global DOC_PROFILE_PROMPT
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=None, help="Only process this doc_id")
    ap.add_argument("--questions", choices=["full", "core"], default="full")
    ap.add_argument("--model", default=None)
    ap.add_argument("--skip-validation-sample", action="store_true")
    args = ap.parse_args()

    model = args.model or default_model()
    run_id = str(uuid.uuid4())
    print(f"Model: {model}  run_id: {run_id}  questions: {args.questions}")

    manifest = load_manifest()
    all_units = load_units()
    prompts = load_prompts()
    common_header = prompts["common_header"]
    questions = prompts["questions"]
    doc_level = prompts["doc_level"]
    DOC_PROFILE_PROMPT = doc_level["DOC_PROFILE"]["prompt"]

    if args.questions == "core":
        questions = {k: v for k, v in questions.items() if k in CORE_QUESTIONS}

    units = [u for u in all_units if args.doc is None or u["doc_id"] == args.doc]
    doc_ids = sorted(set(u["doc_id"] for u in units))
    if args.doc and args.doc not in doc_ids:
        print(f"ERROR: doc_id {args.doc} has no units in coding/units.jsonl", file=sys.stderr)
        sys.exit(1)

    doc_json_cache = {d: load_doc_json(d) for d in doc_ids}
    doc_contexts = {d: build_doc_context(d, manifest, doc_json_cache) for d in doc_ids}

    print(f"Units to code: {len(units)} across {len(doc_ids)} docs; questions: {list(questions)}")

    round1_dir = os.path.join(ROOT, "coding/round1")
    os.makedirs(round1_dir, exist_ok=True)

    # ---- doc profiles first (cheap: 1 call/doc) so this data survives even if
    # the much larger unit-level loop below is interrupted for time reasons ----
    # Resume support: only run profiles for docs without a successful one on disk.
    profiles_path = os.path.join(round1_dir, "doc_profiles.jsonl")
    existing_profiles = {}
    if os.path.exists(profiles_path):
        with open(profiles_path, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                existing_profiles[rec["doc_id"]] = rec
    profile_todo = [d for d in doc_ids
                    if d not in existing_profiles or existing_profiles[d].get("error")]
    if len(profile_todo) < len(doc_ids):
        print(f"Resume: {len(doc_ids) - len(profile_todo)} doc profiles already on disk; "
              f"running {len(profile_todo)}.")

    doc_profile_records = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = {}
        for d in profile_todo:
            header = common_header.replace("{doc_context}", doc_contexts[d]).replace(
                "{passage}", full_doc_text(d, doc_json_cache))
            futs[ex.submit(code_doc_profile, model, run_id, d, header)] = d
        for fut in as_completed(futs):
            doc_profile_records.append(fut.result())
    print(f"Doc profiles: {len(doc_profile_records)} new")
    for r in doc_profile_records:
        existing_profiles[r["doc_id"]] = r
    with open(profiles_path, "w", encoding="utf-8") as f:
        for d in sorted(existing_profiles):
            f.write(json.dumps(existing_profiles[d], ensure_ascii=False) + "\n")
    print(f"Wrote {profiles_path} ({len(existing_profiles)} docs)")

    # ---- unit x question coding ----
    # Resume support: load previously successful records so a re-run after an
    # interruption (e.g. the Ollama Cloud session quota) only spends calls on
    # what is still missing or failed.
    existing_records = {d: [] for d in doc_ids}
    done_pairs = set()
    for d in doc_ids:
        p = os.path.join(round1_dir, f"{d}.jsonl")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not rec.get("error"):
                        existing_records[d].append(rec)
                        done_pairs.add((rec["unit_id"], rec["question"]))
    if done_pairs:
        print(f"Resume: {len(done_pairs)} unit x question pairs already successful; skipping them.")

    tasks = []
    n_truncated = 0
    for u in units:
        passage = u["text"]
        if len(passage) > MAX_UNIT_CHARS:
            passage = passage[:MAX_UNIT_CHARS]
            n_truncated += 1
            print(f"  WARNING: unit {u['unit_id']} is {len(u['text'])} chars, "
                  f"truncated to {MAX_UNIT_CHARS} for coding (segmentation outlier)")
        header = common_header.replace("{doc_context}", doc_contexts[u["doc_id"]]).replace("{passage}", passage)
        for qname, qdef in questions.items():
            if (u["unit_id"], qname) in done_pairs:
                continue
            tasks.append((u, qname, qdef, header, passage))
    if n_truncated:
        print(f"Truncated {n_truncated} oversized unit(s) to {MAX_UNIT_CHARS} chars before coding.")

    print(f"Total LLM calls (unit-level): {len(tasks)}")

    # Write incrementally per doc_id as calls complete, so a slow model that
    # doesn't finish within the time budget still leaves usable partial output
    # on disk instead of losing everything.
    doc_file_handles = {}
    for d in doc_ids:
        doc_file_handles[d] = open(os.path.join(round1_dir, f"{d}.jsonl"), "w", encoding="utf-8")
        for rec in existing_records[d]:
            doc_file_handles[d].write(json.dumps(rec, ensure_ascii=False) + "\n")
        doc_file_handles[d].flush()

    all_records = [r for recs in existing_records.values() for r in recs]
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = {ex.submit(code_unit_question, model, run_id, u, qname, qdef, header, passage): (u["unit_id"], qname)
                for (u, qname, qdef, header, passage) in tasks}
        done_n = 0
        for fut in as_completed(futs):
            recs = fut.result()
            all_records.extend(recs)
            for r in recs:
                fh = doc_file_handles[r["doc_id"]]
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                fh.flush()
            done_n += 1
            if done_n % 10 == 0:
                print(f"  unit-level {done_n}/{len(tasks)} done")

    for fh in doc_file_handles.values():
        fh.close()
    print(f"Wrote {len(doc_file_handles)} coding/round1/<doc_id>.jsonl files ({len(all_records)} records)")

    # ---- definitional_instances.jsonl (merge, chronological) ----
    def_path = os.path.join(round1_dir, "definitional_instances.jsonl")
    existing_def = []
    if os.path.exists(def_path):
        with open(def_path, encoding="utf-8") as f:
            existing_def = [json.loads(l) for l in f]
    # drop existing entries for docs we just recoded (if DEFINITIONAL was in this run)
    if "DEFINITIONAL" in questions:
        existing_def = [r for r in existing_def if r["doc_id"] not in doc_ids]
        new_def = [r for r in all_records if r["question"] == "DEFINITIONAL" and r.get("applies")]
        combined = existing_def + new_def
    else:
        combined = existing_def
    combined.sort(key=lambda r: (manifest.get(r["doc_id"], {}).get("date", ""), r["doc_id"], r["unit_id"]))
    with open(def_path, "w", encoding="utf-8") as f:
        for r in combined:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {def_path} ({len(combined)} definitional instances)")

    # ---- run_meta.json (append run history) ----
    meta_path = os.path.join(round1_dir, "run_meta.json")
    meta = {"runs": []}
    if os.path.exists(meta_path):
        meta = json.load(open(meta_path, encoding="utf-8"))
    quote_checked = [r for r in all_records if r.get("quote_verified") is not None]
    pct_verified = (100 * sum(1 for r in quote_checked if r["quote_verified"]) / len(quote_checked)) if quote_checked else None
    error_records = [r for r in all_records if r.get("error")]
    error_counts = Counter(r["error"] for r in error_records)
    docs_with_success = sorted(set(r["doc_id"] for r in all_records if not r.get("error")))
    pct_calls_succeeded = (100 * (len(all_records) - len(error_records)) / len(all_records)) if all_records else None
    meta["runs"].append({
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "doc_filter": args.doc,
        "questions": list(questions),
        "n_units": len(units),
        "n_unit_question_calls": len(tasks),
        "n_records": len(all_records),
        "n_records_with_error": len(error_records),
        "pct_calls_succeeded": pct_calls_succeeded,
        "n_docs_with_at_least_one_success": len(docs_with_success),
        "n_docs_total": len(doc_ids),
        "top_errors": error_counts.most_common(5),
        "n_doc_profiles": len(doc_profile_records),
        "pct_quote_verified_of_successful_calls": pct_verified,
    })
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"Wrote {meta_path}")

    # ---- validation sample (full corpus run only) ----
    if not args.doc and not args.skip_validation_sample:
        results_by_unit_question = defaultdict(list)
        for r in all_records:
            results_by_unit_question[(r["unit_id"], r["question"])].append(r)
        os.makedirs(os.path.join(ROOT, "coding/validation"), exist_ok=True)
        write_validation_sample(all_units, manifest, doc_json_cache, results_by_unit_question)

    print("DONE.")
    if quote_checked:
        print(f"quote_verified: {pct_verified:.1f}% ({sum(1 for r in quote_checked if r['quote_verified'])}/{len(quote_checked)})")


if __name__ == "__main__":
    main()
