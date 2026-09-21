"""Phase 2: segmentation into coding units + term detection.

Declared method: full scan -> detailed coding of the section that
contains the term. Unit = section (contiguous blocks under the same
top-level heading). Documents with no nominal term -> retrieval of the
distributive claim by lexicon and by embeddings (local embeddinggemma),
tagged with `retrieval` for audit.

Updates in the manifest: term_status (resolves the CHECKs) and provisional
gds_tier (T1 GDS/CDDO authorship · T2 GDS named in the text · T3 absent).
Outputs: coding/units.jsonl · analysis/queries/term_counts.csv
"""
import csv, json, re, unicodedata
from pathlib import Path

import numpy as np
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
LEX = yaml.safe_load((ROOT / "coding" / "lexicon_v1.yaml").read_text(encoding="utf-8"))
OLLAMA = "http://localhost:11434"
EMB_MODEL = "embeddinggemma"
SEM_THRESHOLD = 0.52   # minimum cosine (calibrated to embeddinggemma's scale
                       # on the 'absent' docs: correct hits fall in 0.52-0.63)
SEM_TOPK = 2           # max. semantic passages per doc without a term

rx = lambda pats: [re.compile(p, re.I) for p in pats]
RX_NOM, RX_VAR, RX_DIS = rx(LEX["nominal"]), rx(LEX["variant_nominal"]), rx(LEX["distributive"])


def embed(texts):
    out = []
    for i in range(0, len(texts), 32):
        r = requests.post(f"{OLLAMA}/api/embed", timeout=300,
                          json={"model": EMB_MODEL, "input": texts[i:i + 32]})
        r.raise_for_status()
        out.extend(r.json()["embeddings"])
    v = np.array(out, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def sections(doc):
    """Groups contiguous blocks by top-level heading; title stays in the 1st section."""
    secs, cur, cur_head = [], [], "(start)"
    for b in doc["blocks"]:
        if b["structural_position"] in ("section_heading", "pillar_name"):
            if cur:
                secs.append((cur_head, cur))
            cur_head, cur = b["text"][:120], [b]
        else:
            cur.append(b)
    if cur:
        secs.append((cur_head, cur))
    return secs


def hits(rxs, text):
    out = []
    for r in rxs:
        out += [m.group(0) for m in r.finditer(text)]
    return out


def main():
    rows = list(csv.DictReader((ROOT / "data" / "manifest.csv").open(encoding="utf-8")))
    units, counts = [], []
    probes = embed(LEX["beneficiary_probes"])

    for r in rows:
        doc = json.loads((ROOT / "data" / "text" / f"{r['doc_id']}.json").read_text(encoding="utf-8"))
        full = "\n".join(b["text"] for b in doc["blocks"])
        n_nom, n_var, n_dis = hits(RX_NOM, full), hits(RX_VAR, full), hits(RX_DIS, full)
        counts.append({"doc_id": r["doc_id"], "genre": r["genre"], "speaker": r["speaker"],
                       "family": r["family"], "n_nominal": len(n_nom), "n_variant": len(n_var),
                       "n_distributive": len(n_dis),
                       "nominal_forms": "; ".join(sorted(set(f.lower() for f in n_nom)))})
        # term (resolves CHECK)
        r["term_status"] = "present" if n_nom else ("variant" if n_var else "absent")
        # provisional gds_tier
        low = full.lower()
        if r["speaker"] in ("GDS", "CDDO", "DSIT_and_GDS") or "GDS" in r["speaker"]:
            tier = "T1"
        elif re.search(r"\bgds\b|government digital service|\bi\.ai\b|incubator for (artificial intelligence|ai)|ai playbook|service standard", low):
            tier = "T2"
        else:
            tier = "T3"
        r["gds_tier"] = tier
        r["gds_tier_source"] = "auto_provisional"

        doc_units = []
        for si, (head, blocks) in enumerate(sections(doc)):
            text = "\n".join(b["text"] for b in blocks)
            u_nom, u_var, u_dis = hits(RX_NOM, text), hits(RX_VAR, text), hits(RX_DIS, text)
            if u_nom or u_var or u_dis:
                doc_units.append({
                    "unit_id": f"{r['doc_id']}::s{si:02d}", "doc_id": r["doc_id"],
                    "heading": head, "block_ids": [b["block_id"] for b in blocks],
                    "text": text, "retrieval": "lexicon",
                    "hits_nominal": u_nom, "hits_variant": u_var, "hits_distributive": u_dis})
        # semantic retrieval only where the lexicon found nothing nominal
        if not n_nom:
            secs = sections(doc)
            paras = [(si, head, "\n".join(b["text"] for b in blocks))
                     for si, (head, blocks) in enumerate(secs)
                     if len("\n".join(b["text"] for b in blocks)) > 200]
            if paras:
                vecs = embed([p[2][:1500] for p in paras])
                sim = (vecs @ probes.T).max(axis=1)
                got = {u["unit_id"] for u in doc_units}
                order = np.argsort(-sim)[:SEM_TOPK]
                for j in order:
                    if sim[j] < SEM_THRESHOLD:
                        continue
                    si, head, text = paras[j]
                    uid = f"{r['doc_id']}::s{si:02d}"
                    if uid in got:
                        continue
                    doc_units.append({
                        "unit_id": uid, "doc_id": r["doc_id"], "heading": head,
                        "block_ids": [b["block_id"] for b in secs[si][1]],
                        "text": text, "retrieval": "semantic",
                        "similarity": round(float(sim[j]), 3),
                        "hits_nominal": [], "hits_variant": [], "hits_distributive": []})
        # short documents with no unit at all -> the whole doc is the unit
        # (SO3 coverage: the intra-family comparison needs all records,
        # with or without term; short genres — PRCO/MOU/BLOG/WMS — are a single rhetorical piece)
        if not doc_units and len(full) <= 9000:
            doc_units.append({
                "unit_id": f"{r['doc_id']}::full", "doc_id": r["doc_id"],
                "heading": doc["blocks"][0]["text"][:120],
                "block_ids": [b["block_id"] for b in doc["blocks"]],
                "text": full, "retrieval": "full_short_doc",
                "hits_nominal": [], "hits_variant": [], "hits_distributive": []})
        units.extend(doc_units)

    with (ROOT / "data" / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    with (ROOT / "coding" / "units.jsonl").open("w", encoding="utf-8") as f:
        for u in units:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    qdir = ROOT / "analysis" / "queries"; qdir.mkdir(parents=True, exist_ok=True)
    with (qdir / "term_counts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(counts[0].keys()))
        w.writeheader(); w.writerows(counts)

    from collections import Counter
    print(f"{len(units)} coding units "
          f"(lexicon: {sum(1 for u in units if u['retrieval']=='lexicon')}, "
          f"semantic: {sum(1 for u in units if u['retrieval']=='semantic')})")
    print("term_status:", dict(Counter(r["term_status"] for r in rows)))
    print("gds_tier:", dict(Counter(r["gds_tier"] for r in rows)))
    zero = [r["doc_id"] for r in rows if r["term_status"] == "absent"]
    print(f"docs with no nominal term (zero-count): {len(zero)}")


if __name__ == "__main__":
    main()
