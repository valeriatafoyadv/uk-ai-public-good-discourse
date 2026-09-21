#!/usr/bin/env python
"""Phase 5 (preparation) -- Round 2 consolidation, DRAFT for the author's review.

Two outputs, both DRAFT / provisional:

1. coding/guidebook_draft.yaml -- for each core question, embeds the
   answer_summary values from coding/round1/*.jsonl with embeddinggemma,
   groups them by cosine similarity (threshold ~0.75, simple union-find),
   and writes candidate clusters. The 8 beneficiary nodes from the NVivo plan
   (Beneficiary_PublicGood, _PublicBenefit, _Taxpayer, _Distributive,
   _Sovereignty, _PublicInterest, _WorkingPeople, _Economy) are used as seeds
   to name BENEFICIARY clusters when a cluster's content matches them.

2. analysis/metaphors_report.md -- aggregates METAPHOR instances from
   coding/round1/*.jsonl by expression, with a suggested source/target domain,
   TARGET IS SOURCE formula, tentative Lakoff & Johnson (1980) type, and
   what each mapping highlights/hides.

The final decision (cluster names, definitions, inclusion rules, domain
assignments) belongs to the author -- this script only proposes. Both outputs
carry a loud coverage warning if the latest coding/round1/run_meta.json run
did not complete for the full corpus, so a partial Round 1 is never mistaken
for full corpus coverage.

Usage:
    .venv/bin/python scripts/06_consolidate.py
"""
import csv
import glob
import json
import os
import re
from collections import Counter, defaultdict

import numpy as np
import requests
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLLAMA_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "embeddinggemma"
SIM_THRESHOLD = 0.75

CORE_QUESTIONS = [
    "BENEFICIARY", "MECHANISM", "SAFEGUARD", "RESPONSIBILITY",
    "PROJECTED_FUTURE", "ACTANTS", "NATURALISED_ORDER",
]

BENEFICIARY_SEEDS = {
    "Beneficiary_PublicGood": ["public good", "the public good", "society", "everyone"],
    "Beneficiary_PublicBenefit": ["public benefit", "benefits", "wider public"],
    "Beneficiary_Taxpayer": ["taxpayer", "taxpayers", "value for money"],
    "Beneficiary_Distributive": ["every citizen", "all", "everyone benefits", "distributed"],
    "Beneficiary_Sovereignty": ["sovereign", "sovereignty", "national capability", "the uk"],
    "Beneficiary_PublicInterest": ["public interest"],
    "Beneficiary_WorkingPeople": ["working people", "workers", "workforce"],
    "Beneficiary_Economy": ["the economy", "growth", "businesses", "industry"],
}


def load_records():
    records = []
    for path in sorted(glob.glob(os.path.join(ROOT, "coding/round1/*.jsonl"))):
        if os.path.basename(path) in ("doc_profiles.jsonl", "definitional_instances.jsonl"):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                records.append(json.loads(line))
    return records


def embed(texts, batch_size=32):
    vecs = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = requests.post(OLLAMA_URL, json={"model": EMBED_MODEL, "input": batch}, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        vecs.extend(data["embeddings"])
    return np.array(vecs, dtype=np.float32)


class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def cosine_sim_matrix(vecs):
    norm = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
    return norm @ norm.T


def cluster_question(qname, recs):
    """recs: list of dicts with answer_summary, verbatim_quote, unit_id, doc_id."""
    texts = [r["answer_summary"] for r in recs if r.get("answer_summary")]
    recs = [r for r in recs if r.get("answer_summary")]
    if not recs:
        return []
    vecs = embed(texts)
    sims = cosine_sim_matrix(vecs)
    n = len(recs)
    uf = UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if sims[i, j] >= SIM_THRESHOLD:
                uf.union(i, j)

    groups = {}
    for i in range(n):
        root = uf.find(i)
        groups.setdefault(root, []).append(i)

    clusters = []
    for root, idxs in groups.items():
        members = [recs[i] for i in idxs]
        clusters.append(members)
    clusters.sort(key=len, reverse=True)
    return clusters


def name_candidate(qname, members):
    """Heuristic short snake_case label from the most common short field value."""
    labels = []
    key_map = {
        "BENEFICIARY": "beneficiary", "MECHANISM": "mechanism", "SAFEGUARD": "safeguard",
        "RESPONSIBILITY": "responsible", "PROJECTED_FUTURE": "future",
        "ACTANTS": "actant", "NATURALISED_ORDER": "order",
    }
    field = key_map.get(qname)
    for m in members:
        summ = m.get("answer_summary", "")
        if field:
            mo = re.search(rf"{field}=([^;]+)", summ)
            if mo:
                labels.append(mo.group(1).strip().lower())
    if not labels:
        labels = [m.get("answer_summary", "cluster")[:30] for m in members]

    # majority vote
    from collections import Counter
    common = Counter(labels).most_common(1)[0][0]
    slug = re.sub(r"[^a-z0-9]+", "_", common).strip("_")[:40] or "unnamed_cluster"

    if qname == "BENEFICIARY":
        for seed_name, keywords in BENEFICIARY_SEEDS.items():
            if any(kw in common for kw in keywords):
                return seed_name
    return slug


def coverage_warning():
    """If coding/round1/run_meta.json shows the latest Round 1 run did not
    complete for the full corpus, surface that loudly here so a partial
    Round 1 is never mistaken for full corpus coverage."""
    meta_path = os.path.join(ROOT, "coding/round1/run_meta.json")
    if not os.path.exists(meta_path):
        return None
    meta = json.load(open(meta_path, encoding="utf-8"))
    runs = meta.get("runs", [])
    if not runs:
        return None
    run = runs[-1]
    pct = run.get("pct_calls_succeeded")
    n_ok = run.get("n_docs_with_at_least_one_success")
    n_total = run.get("n_docs_total")
    if pct is not None and pct < 99.5:
        return (
            f"COVERAGE WARNING: the latest Round 1 run only succeeded on "
            f"{pct:.1f}% of calls ({n_ok}/{n_total} documents with at least "
            "one successful record) -- see coding/round1/run_meta.json "
            "'status' for why. Clusters and counts below are computed ONLY "
            "from the records that did succeed and are NOT corpus-wide. "
            "Re-run scripts/06_consolidate.py after completing Round 1."
        )
    return None


def main():
    records = load_records()
    if not records:
        print("No records in coding/round1/*.jsonl yet -- run scripts/05_code.py first.")
        return

    by_q = {}
    for r in records:
        by_q.setdefault(r.get("question"), []).append(r)

    warning = coverage_warning()
    if warning:
        print(warning)

    # Ollama (embeddinggemma) is required for clustering. Check ONCE, up front:
    # if it's unreachable, skip clustering entirely and leave guidebook_draft.yaml
    # untouched on disk (never overwrite good, previously-computed clusters with
    # an empty/partial run just because this machine has no Ollama). The metaphor
    # report needs no embeddings, so it always regenerates regardless.
    ollama_available = True
    try:
        requests.post(OLLAMA_URL, json={"model": EMBED_MODEL, "input": ["ping"]}, timeout=5).raise_for_status()
    except requests.exceptions.RequestException:
        ollama_available = False

    if not ollama_available:
        print(f"Ollama ({EMBED_MODEL}) unreachable at {OLLAMA_URL} -- skipping guidebook "
              "clustering entirely. coding/guidebook_draft.yaml is left UNCHANGED on disk "
              "(not overwritten with an empty/partial result). Re-run this script on a "
              "machine with Ollama running to (re)generate clusters, e.g. after adding new "
              "documents' Round 1 records. Proceeding to regenerate metaphors_report.md, "
              "which does not require embeddings.")
    else:
        guidebook = {
            "status": "DRAFT_pending_author",
            "generated_from": "coding/round1/*.jsonl",
            "similarity_threshold": SIM_THRESHOLD,
            "embedding_model": EMBED_MODEL,
            "note": (
                "Clusters proposed automatically by cosine similarity of "
                "answer_summary. candidate_name is a heuristic label -- "
                "the author decides the final name, definition and "
                "inclusion/exclusion rule in guidebook.yaml."
            ),
            "questions": {},
        }
        if warning:
            guidebook["coverage_warning"] = warning

        for qname in CORE_QUESTIONS:
            recs = [r for r in by_q.get(qname, []) if r.get("applies")]
            if not recs:
                guidebook["questions"][qname] = {"clusters": [], "n_applies_true": 0}
                continue
            clusters = cluster_question(qname, recs)
            q_out = []
            for cl in clusters:
                name = name_candidate(qname, cl)
                examples = []
                for m in cl[:3]:
                    examples.append(m.get("verbatim_quote") or "")
                q_out.append({
                    "candidate_name": name,
                    "n_instances": len(cl),
                    "example_quotes": examples,
                    "member_unit_ids": sorted(set(m["unit_id"] for m in cl)),
                    "status": "DRAFT_pending_author",
                })
            guidebook["questions"][qname] = {
                "n_applies_true": len(recs),
                "n_clusters": len(q_out),
                "clusters": q_out,
            }
            print(f"{qname}: {len(recs)} instances -> {len(q_out)} clusters")

        out_path = os.path.join(ROOT, "coding/guidebook_draft.yaml")
        with open(out_path, "w", encoding="utf-8") as f:
            yaml.dump(guidebook, f, allow_unicode=True, sort_keys=False, width=100)
        print(f"Wrote {out_path}")

    write_metaphors_report(warning)


# ---------------------------------------------------------------------------
# Metaphor report (analysis/metaphors_report.md)
# ---------------------------------------------------------------------------

def load_manifest():
    manifest = {}
    with open(os.path.join(ROOT, "data/manifest.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            manifest[row["doc_id"]] = row
    return manifest


def load_metaphor_records():
    records = []
    for path in sorted(glob.glob(os.path.join(ROOT, "coding/round1/*.jsonl"))):
        base = os.path.basename(path)
        if base in ("doc_profiles.jsonl", "definitional_instances.jsonl"):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("question") == "METAPHOR" and r.get("applies") and r.get("instance_data"):
                    inst = json.loads(r["instance_data"])
                    inst["doc_id"] = r["doc_id"]
                    inst["unit_id"] = r["unit_id"]
                    records.append(inst)
    return records


def normalize_expr(expr):
    return re.sub(r"\s+", " ", (expr or "").strip().lower())


LJ_LABELS = {
    "estructural": "structural", "orientacional": "orientational",
    "ontologica": "ontological", "ontológica": "ontological",
    "personificacion": "personification", "personificación": "personification",
}


def write_metaphors_report(coverage_warning_text):
    manifest = load_manifest()
    records = load_metaphor_records()
    out_path = os.path.join(ROOT, "analysis/metaphors_report.md")

    if not records:
        print("No METAPHOR records found in coding/round1/*.jsonl -- skipping metaphors_report.md.")
        return

    groups = defaultdict(list)
    for inst in records:
        key = normalize_expr(inst.get("expression"))
        if key:
            groups[key].append(inst)
    ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))

    lines = []
    if coverage_warning_text:
        docs_covered = sorted(set(r["doc_id"] for r in records))
        lines.append("> **STATUS: INCOMPLETE -- NOT corpus-wide.** ")
        lines.append(
            f"{coverage_warning_text} The frequencies and domain suggestions "
            f"below reflect ONLY: {', '.join(docs_covered)}. Re-run "
            "`scripts/05_code.py` to completion, then `scripts/06_consolidate.py` "
            "again, before treating this as a corpus-wide finding.\n\n"
        )
    lines.append("# Metaphor report — corpus-wide source/target domain suggestions\n\n")
    lines.append(
        "**SUGGESTIONS for the author's validation — the final domain assignment "
        "is interpretive.** This report aggregates the metaphorical expressions "
        "identified by the LLM (question METAPHOR, MIP-based identification; "
        "Pragglejaz Group 2007) across the corpus. For each expression it lists a "
        "suggested source domain, target domain, the `TARGET IS SOURCE` formula, "
        "a tentative Lakoff & Johnson (1980) type, and what the mapping "
        "foregrounds/backgrounds (the latter feeds the NATURALISED_ORDER question "
        "and Lears 1985 on naturalisation). Domain names, the L&J type, and the "
        "highlights/hides gloss are the model's *suggestion* per instance; where "
        "instances of the same expression disagreed, the majority value is shown "
        "and disagreement is noted. The author decides the final domain "
        "assignment, groups related expressions into domains, and corrects "
        "mislabelled instances before this feeds any thesis chapter.\n\n"
    )
    lines.append(f"Generated from {len(records)} METAPHOR instances "
                  f"(applies=true) across {len(set(r['doc_id'] for r in records))} document(s).\n\n")
    lines.append("## Top expressions by frequency\n\n")

    for rank, (expr, insts) in enumerate(ranked[:20], start=1):
        n = len(insts)
        docs = sorted(set(i["doc_id"] for i in insts))
        speakers = sorted(set(manifest.get(d, {}).get("speaker", "?") for d in docs))
        families = sorted(set(manifest.get(d, {}).get("family", "None") for d in docs) - {"None", ""})

        source_domains = Counter(normalize_expr(i.get("suggested_source_domain", "")) for i in insts)
        target_domains = Counter(normalize_expr(i.get("suggested_target_domain", "")) for i in insts)
        formulas = Counter((i.get("formula") or "").strip() for i in insts)
        lj_types = Counter((i.get("lj_type") or "").strip().lower() for i in insts)
        highlights = Counter((i.get("highlights") or "").strip() for i in insts)
        hides = Counter((i.get("hides") or "").strip() for i in insts)

        top_source = source_domains.most_common(1)[0][0] if source_domains else "?"
        top_target = target_domains.most_common(1)[0][0] if target_domains else "?"
        top_formula = formulas.most_common(1)[0][0] if formulas else "?"
        top_lj = lj_types.most_common(1)[0][0] if lj_types else "?"
        top_lj_en = LJ_LABELS.get(top_lj, top_lj)
        top_highlight = highlights.most_common(1)[0][0] if highlights else ""
        top_hide = hides.most_common(1)[0][0] if hides else ""

        disagreement_note = ""
        if len(source_domains) > 1 or len(target_domains) > 1:
            disagreement_note = " *(source/target domain varied across instances; majority shown.)*"

        lines.append(f"### {rank}. \"{insts[0].get('expression')}\" (n={n})\n\n")
        lines.append(f"- **Suggested formula:** {top_formula or (top_target.upper() + ' IS ' + top_source.upper())}\n")
        lines.append(f"- **Suggested source domain:** {top_source.upper() or '?'}\n")
        lines.append(f"- **Suggested target domain:** {top_target.upper() or '?'}\n")
        lines.append(f"- **Tentative L&J type:** {top_lj_en or '?'}{disagreement_note}\n")
        lines.append(f"- **What it highlights:** {top_highlight or '(not specified)'}\n")
        lines.append(f"- **What it hides:** {top_hide or '(not specified)'}\n")
        lines.append(f"- **Count:** {n} instance(s) in {len(docs)} document(s)\n")
        lines.append(f"- **Speakers:** {', '.join(speakers)}" +
                      (f"  |  **Company families:** {', '.join(families)}" if families else "") + "\n")
        lines.append(f"- **Documents:** {', '.join(docs[:6])}" + (" ..." if len(docs) > 6 else "") + "\n")
        lines.append("- **Evidence quotes:**\n")
        seen_quotes = []
        for i in insts:
            q = (i.get("verbatim_quote") or "").strip()
            if q and q not in seen_quotes:
                seen_quotes.append(q)
            if len(seen_quotes) >= 3:
                break
        for q in seen_quotes:
            src_doc = next(i["doc_id"] for i in insts if i.get("verbatim_quote") == q)
            lines.append(f"  - \"{q}\" ({src_doc})\n")
        lines.append("\n")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"Wrote {out_path} ({len(ranked)} distinct expressions, top {min(20, len(ranked))} shown)")


if __name__ == "__main__":
    main()
