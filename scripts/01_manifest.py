"""Phase 0: builds data/manifest.csv from 'Document Analysis v1.xlsx'.

Corpus v1 = rows from 'Official_Document Selection' BEFORE the
"EITHER BRING" marker (decisions made). The pending A/B blocks are not included.
Decision by the author 2026-08-29: the CONTEXT_ row enters the corpus (Speaker=External_adviser).
"""
import csv
import re
import sys
from pathlib import Path

import openpyxl

XLSX = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data" / "Document Analysis v1.xlsx"
OUT = Path(__file__).resolve().parent.parent / "data" / "manifest.csv"

FAMILIES = ["Anthropic", "Cohere", "OpenAI", "DeepMind", "ElevenLabs"]
GENRES = {"STRAT", "MOU", "PRGOV", "PRCO", "BLOG", "WMS", "REG"}


def norm_term(v):
    if v is None:
        return "check"
    s = str(v).strip().lower()
    if s in {"1", "1.0", "present"}:
        return "present"
    if s in {"0", "0.0", "absent"}:
        return "absent"
    if "variant" in s or "variation" in s:
        return "variant"
    if "check" in s:
        return "check"
    return "check"


def norm_speaker(actor, genre, family):
    a = (actor or "").lower()
    if "matt clifford" in a or "external" in a:
        return "External_adviser"
    if genre == "MOU":
        return f"DSIT_and_{family}" if family else "DSIT_and_company"
    if genre == "PRCO":
        return family or "company"
    if "cddo" in a:
        return "CDDO"
    if "prime minister" in a or "pmo" in a or "downing street" in a:
        return "PMO"
    has_gds = "gds" in a or "government digital service" in a or "digital officer" in a
    has_dsit = "dsit" in a or "science, innovation" in a
    if has_gds and has_dsit:
        return "DSIT_and_GDS"
    if has_gds:
        return "GDS"
    if has_dsit:
        return "DSIT"
    return "REVIEW"


def doc_family(name):
    for f in FAMILIES:
        if f.lower() in name.lower():
            return f
    return "None"


def main():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb["Official_Document Selection"]
    rows = list(ws.iter_rows(values_only=True))

    records, notes = [], []
    for excel_row, r in enumerate(rows[1:], start=2):
        cells = ["" if v is None else str(v).strip() for v in r]
        joined = " ".join(cells)
        if "EITHER BRING" in joined.upper():
            notes.append(f"Cutoff marker found at Excel row {excel_row}.")
            break
        if not any(cells):
            continue
        name = cells[1]
        if not name:
            notes.append(f"Excel row {excel_row}: no NVIVO_Document_Name, skipped ({joined[:80]!r}).")
            continue
        m = re.match(r"^(CONTEXT_)?(\d{4}-\d{2}-\d{2})_([A-Z]+)_", name)
        if not m:
            notes.append(f"Excel row {excel_row}: name does not parse ({name!r}), REVIEW.")
            continue
        is_context_name = bool(m.group(1))
        date, genre = m.group(2), m.group(3)
        if genre not in GENRES:
            notes.append(f"Excel row {excel_row}: genre {genre!r} outside the set, REVIEW.")
        family = doc_family(name)
        actor = cells[3]
        speaker = norm_speaker(actor, genre, family)
        url = cells[6]
        if not url.startswith("http"):
            notes.append(f"{name}: no valid URL ({url[:60]!r}).")
        archive = cells[15] if len(cells) > 15 and cells[15].startswith("http") else ""
        records.append({
            "doc_id": name,
            "excel_row": excel_row,
            "date": date,
            "genre": genre,
            "actor_raw": actor,
            "speaker": speaker,
            "side": cells[4],
            "family": family,
            "gds_tier": "",  # T1/T2/T3 — assigned by the author (NVivo plan, column T)
            "stage": cells[11].replace(".0", "") if cells[11] else "",
            "term_status": norm_term(r[12]),
            "url": url,
            "archive_url": archive,
            "corpus_version": 1,
            "is_context": is_context_name,  # enters the corpus per decision 2026-08-29
            "fetch_status": "pending",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        w.writeheader()
        w.writerows(records)

    print(f"Corpus v1: {len(records)} documents -> {OUT}")
    from collections import Counter
    for field in ("genre", "speaker", "term_status", "family"):
        print(f"  {field}: {dict(Counter(x[field] for x in records))}")
    dupes = [d for d, c in __import__('collections').Counter(x['doc_id'] for x in records).items() if c > 1]
    if dupes:
        print(f"  DUPLICATES: {dupes}")
    print("\nNotes:")
    for n in notes:
        print(f"  - {n}")


if __name__ == "__main__":
    sys.exit(main())
