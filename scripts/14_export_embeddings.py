"""Exports the Ollama embeddings to versioned files so the analysis is
reproducible on machines without Ollama (or with a different model build).

Persists, under data/embeddings/:
  sections_embeddinggemma.npz   -- one L2-normalised vector per document section
                                   (same sections() segmentation as 04_segment.py)
  sections_index.json           -- row order: {doc_id, section_idx, heading}
  probes_embeddinggemma.npz     -- the beneficiary_probes vectors (lexicon v1)
  meta.json                     -- model, dimension, date, corpus version
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
seg = __import__("04_segment")  # reuses embed(), sections(), LEX

OUT = ROOT / "data" / "embeddings"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    index, texts = [], []
    for p in sorted((ROOT / "data" / "text").glob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        for si, (head, blocks) in enumerate(seg.sections(doc)):
            text = "\n".join(b["text"] for b in blocks)
            if len(text) < 40:
                continue
            index.append({"doc_id": p.stem, "section_idx": si, "heading": head})
            texts.append(text[:1500])

    print(f"Embedding {len(texts)} sections with {seg.EMB_MODEL}...")
    vecs = seg.embed(texts)
    np.savez_compressed(OUT / "sections_embeddinggemma.npz", vectors=vecs)
    (OUT / "sections_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    probes = seg.embed(seg.LEX["beneficiary_probes"])
    np.savez_compressed(OUT / "probes_embeddinggemma.npz", vectors=probes,
                        )
    (OUT / "meta.json").write_text(json.dumps({
        "model": seg.EMB_MODEL, "dim": int(vecs.shape[1]),
        "n_sections": len(index), "normalisation": "L2",
        "truncation_chars": 1500, "lexicon_version": seg.LEX["version"],
        "probes": seg.LEX["beneficiary_probes"],
    }, indent=1))
    print(f"Wrote {vecs.shape} section vectors + {probes.shape} probe vectors -> {OUT}")


if __name__ == "__main__":
    main()
