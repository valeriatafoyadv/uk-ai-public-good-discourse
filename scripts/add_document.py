"""Phase 7: incremental document intake into the corpus.

    add_document.py <url> [--family Anthropic|Cohere|OpenAI|DeepMind|ElevenLabs]
                    [--genre STRAT|MOU|PRGOV|PRCO|BLOG|WMS|REG]
                    [--dry-run] [--yes]

1. Admission checklist (rules from the `method` sheet, applied as an
   explicit filter BEFORE writing anything to disk): Jan-2024/Jul-2026
   window, speaker-no-publisher, functional boundary of the digital centre,
   blog criterion, producer-vs-scrutineer, written-vs-spoken. `--dry-run`
   prints the checklist and stops without touching anything.
2. If the checklist passes (or is forced with `--yes`): downloads (browser
   UA, archive.org fallback), extracts into the data/text/ schema (same
   block format as 02a/02b: title/section_heading/body/quotation), appends
   the row to the manifest (corpus_version = next), generates its coding
   units in coding/units.jsonl with the same logic as 04_segment.py, and
   recalculates the network and the term counts.

Nothing gets in automatically: without --yes, interactive confirmation is
requested after showing the checklist. LLM coding (Phase 4) of the new doc
is NOT triggered here — it's left as a note in the final report.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "manifest.csv"
TEXT_DIR = ROOT / "data" / "text"
RAW_DIR = ROOT / "data" / "raw"
UNITS = ROOT / "coding" / "units.jsonl"
LEXICON = ROOT / "coding" / "lexicon_v1.yaml"
TERM_COUNTS = ROOT / "analysis" / "queries" / "term_counts.csv"
NETWORK_HTML = ROOT / "analysis" / "networks" / "authorship_family_map.html"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"}
TIMEOUT = 30

WINDOW_START = date(2024, 1, 1)
WINDOW_END = date(2026, 7, 31)

FAMILIES = ["Anthropic", "Cohere", "OpenAI", "DeepMind", "ElevenLabs", "NVIDIA", "Cisco", "Synthesia"]
COMPANY_DOMAINS = {
    "anthropic.com": "Anthropic",
    "cohere.com": "Cohere",
    "openai.com": "OpenAI",
    "deepmind.google": "DeepMind",
    "elevenlabs.io": "ElevenLabs",
    "nvidia.com": "NVIDIA",
    "nvidianews.nvidia.com": "NVIDIA",
    "cisco.com": "Cisco",
    "news-blogs.cisco.com": "Cisco",
    "synthesia.io": "Synthesia",
}
GOV_DOMAINS = ("gov.uk", "parliament.uk", "campaign.gov.uk")
SCRUTINY_DOMAINS = (
    "committees.parliament.uk", "nao.org.uk", "ico.org.uk", "publicaccountscommittee",
)
HANSARD_DOMAINS = ("hansard.parliament.uk",)
GENRES = {"STRAT", "MOU", "PRGOV", "PRCO", "BLOG", "WMS", "REG"}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def clean_text(s: str) -> str:
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def slugify(title: str) -> str:
    """Converts a title into a short CamelCase slug, matching the existing doc_id style."""
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z0-9]+", t)
    stop = {"the", "a", "an", "of", "and", "to", "for", "in", "on", "with", "uk"}
    keep = [w for w in words if w.lower() not in stop] or words
    slug = "".join(w[:1].upper() + w[1:] for w in keep[:6])
    return slug[:60] or "Untitled"


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def fetch(session, url):
    """GET with retries; returns requests.Response or raises the exception."""
    last_exc = None
    for attempt in range(3):
        try:
            r = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise last_exc


def wayback_fallback(session, url):
    """Queries the Wayback availability API; returns snapshot url or None."""
    try:
        r = session.get("https://archive.org/wayback/available", params={"url": url}, timeout=20)
        r.raise_for_status()
        data = r.json()
        closest = (data.get("archived_snapshots") or {}).get("closest")
        if closest and closest.get("available"):
            return closest.get("url"), closest.get("timestamp")
    except Exception:  # noqa: BLE001
        pass
    return None, None


# ---------------------------------------------------------------------------
# Admission checklist
# ---------------------------------------------------------------------------

def guess_date(soup: BeautifulSoup, resp) -> str | None:
    """Heuristic: date meta tags, then gov.uk 'Published' text."""
    for sel, attr in [
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="date"]', "content"),
        ('meta[name="DC.date.issued"]', "content"),
        ('meta[property="og:updated_time"]', "content"),
        ('time[datetime]', "datetime"),
    ]:
        el = soup.select_one(sel)
        if el and el.get(attr):
            m = re.search(r"\d{4}-\d{2}-\d{2}", el.get(attr))
            if m:
                return m.group(0)
    # gov.uk: "Published <D Month Year>"
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Published\s*:?\s*(\d{1,2}\s+\w+\s+\d{4})", text)
    if m:
        try:
            d = datetime.strptime(m.group(1), "%d %B %Y")
            return d.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def run_checklist(url: str, session) -> dict:
    """Evaluates the admission rules and returns {rules: [...], fetched: {...}}."""
    rules = []
    fetched = {"ok": False, "soup": None, "resp": None, "is_pdf": False,
               "text": "", "title": url, "used_archive": False}

    def add(name, status, detail):
        rules.append({"rule": name, "status": status, "detail": detail})

    # --- download attempt (read-only, nothing written to disk) ---
    try:
        resp = fetch(session, url)
        is_pdf = "pdf" in resp.headers.get("Content-Type", "").lower() or url.lower().endswith(".pdf")
        fetched.update(ok=True, resp=resp, is_pdf=is_pdf)
        if not is_pdf:
            soup = BeautifulSoup(resp.content, "lxml")
            fetched["soup"] = soup
            fetched["text"] = clean_text(soup.get_text(" ", strip=True))
            h1 = soup.find("h1")
            if h1 and clean_text(h1.get_text()):
                fetched["title"] = clean_text(h1.get_text())
            elif soup.title:
                fetched["title"] = clean_text(soup.title.get_text())
        fetch_note = f"direct download OK (status {resp.status_code})"
    except Exception as exc:  # noqa: BLE001
        arch_url, ts = wayback_fallback(session, url)
        if arch_url:
            try:
                resp = fetch(session, arch_url)
                is_pdf = "pdf" in resp.headers.get("Content-Type", "").lower() or url.lower().endswith(".pdf")
                fetched.update(ok=True, resp=resp, is_pdf=is_pdf, used_archive=True)
                if not is_pdf:
                    soup = BeautifulSoup(resp.content, "lxml")
                    fetched["soup"] = soup
                    fetched["text"] = clean_text(soup.get_text(" ", strip=True))
                fetch_note = f"direct download failed ({exc}); recovered via archive.org snapshot {ts}"
            except Exception as exc2:  # noqa: BLE001
                fetch_note = f"direct download failed ({exc}); archive.org fallback also failed ({exc2})"
        else:
            fetch_note = f"direct download failed ({exc}); no snapshot on archive.org"
    add("Download (direct / archive.org fallback)", "pass" if fetched["ok"] else "fail", fetch_note)

    dom = domain_of(url)

    # Rule 1 — time window / supersession
    doc_date = guess_date(fetched["soup"], fetched.get("resp")) if fetched["soup"] else None
    if doc_date:
        try:
            d = datetime.strptime(doc_date, "%Y-%m-%d").date()
            in_window = WINDOW_START <= d <= WINDOW_END
            add("Rule 1 — Jan-2024/Jul-2026 window", "pass" if in_window else "fail",
                f"date detected {doc_date}" + ("" if in_window else " (outside window)"))
        except ValueError:
            add("Rule 1 — Jan-2024/Jul-2026 window", "no-determinable", f"date not parseable: {doc_date!r}")
    else:
        add("Rule 1 — Jan-2024/Jul-2026 window", "no-determinable",
            "could not automatically detect the publication date; confirm manually")

    # Rule 3 — speaker, not publisher (whose voice is it?)
    if dom in COMPANY_DOMAINS:
        add("Rule 3 — speaker-no-publisher", "pass",
            f"company domain ({dom}) → voice = {COMPANY_DOMAINS[dom]}")
    elif any(dom == g or dom.endswith("." + g) for g in GOV_DOMAINS):
        add("Rule 3 — speaker-no-publisher", "pass",
            f"government domain ({dom}) → voice = government; confirm exact actor (GDS/DSIT/CDDO/PMO)")
    else:
        add("Rule 3 — speaker-no-publisher", "no-determinable",
            f"domain {dom!r} is neither gov.uk/parliament.uk nor an MoU company domain; "
            "verify that the text's voice is the actor's and not a third party reporting on them")

    # Rule 4 — functional boundary of the digital centre
    kw = r"\bgds\b|government digital service|\bi\.ai\b|incubator for (artificial intelligence|ai)|" \
         r"dsit\b|science, innovation and technology|digital government|public services?.{0,20}\bai\b|" \
         r"memorandum of understanding|ai opportunities"
    low = fetched["text"].lower()
    if low and re.search(kw, low):
        add("Rule 4 — functional boundary of the digital centre", "pass",
            "the text mentions GDS/DSIT/i.AI or digital government / AI in public services")
    elif low:
        add("Rule 4 — functional boundary of the digital centre", "no-determinable",
            "no digital-centre keywords detected; review manually whether it falls within scope")
    else:
        add("Rule 4 — functional boundary of the digital centre", "no-determinable",
            "no extracted text to evaluate (PDF or failed download)")

    # Rule 5 — blog criterion
    if "/blog" in urlparse(url).path.lower() or "blog." in dom:
        is_recognised_blog = dom.startswith("gds.blog") or dom in COMPANY_DOMAINS or "blog." + dom.split(".", 1)[-1] == dom
        recognised = dom.startswith("gds.blog") or any(c in dom for c in COMPANY_DOMAINS)
        add("Rule 5 — blog criterion", "pass" if recognised else "no-determinable",
            f"blog URL ({dom}); " + ("recognized institutional blog (GDS / MoU company)"
             if recognised else "unrecognized blog — confirm it is institutional voice, not personal/third-party"))
    else:
        add("Rule 5 — blog criterion", "pass", "not a blog URL (not applicable)")

    # producer-vs-scrutineer
    if any(s in dom for s in SCRUTINY_DOMAINS):
        add("Producer vs. scrutineer", "fail",
            f"scrutiny/audit domain ({dom}) → context, NOT corpus")
    else:
        add("Producer vs. scrutineer", "pass", "not a parliamentary scrutiny/audit body")

    # written-vs-spoken (Hansard excluded)
    if any(h in dom for h in HANSARD_DOMAINS) or "hansard" in url.lower():
        add("Written vs. spoken (Hansard excluded)", "fail",
            "Hansard / transcript of spoken remarks → outside the corpus")
    else:
        add("Written vs. spoken (Hansard excluded)", "pass", "not a Hansard transcript")

    fetched["guessed_date"] = doc_date
    return {"rules": rules, "fetched": fetched}


def print_checklist(url, result):
    print(f"\n=== Admission checklist — {url} ===")
    for r in result["rules"]:
        mark = {"pass": "PASS", "fail": "FAIL", "no-determinable": "NOT DETERMINABLE"}[r["status"]]
        print(f"  [{mark:16s}] {r['rule']}")
        print(f"                     {r['detail']}")
    fails = [r for r in result["rules"] if r["status"] == "fail"]
    print()
    if fails:
        print(f"RESULT: {len(fails)} rule(s) FAILED — requires explicit review by the author before admitting.")
    else:
        nd = [r for r in result["rules"] if r["status"] == "no-determinable"]
        print(f"RESULT: no hard failures. {len(nd)} rule(s) not determinable — the author decides.")


# ---------------------------------------------------------------------------
# Extraction to data/text schema
# ---------------------------------------------------------------------------

CAPTURE_TAGS = {"h1", "h2", "h3", "h4", "p", "li", "blockquote"}
SKIP_TAGS = {"script", "style", "nav", "aside", "footer", "form", "figure", "table"}


def walk_html(el):
    for child in el.find_all(recursive=False):
        name = getattr(child, "name", None)
        if name is None:
            continue
        if name in CAPTURE_TAGS:
            yield child
        elif name in SKIP_TAGS:
            continue
        else:
            yield from walk_html(child)


def get_container(soup):
    for sel in ("article .entry-content", ".entry-content", "#content .govspeak",
                "main .govspeak", "#content", "main", "article"):
        el = soup.select_one(sel)
        if el is not None and len(el.get_text(strip=True)) > 200:
            return el
    return soup.body or soup


def extract_html_blocks(soup, title_text):
    container = get_container(soup)
    blocks, heading_stack, n = [], {}, 0

    def next_id():
        nonlocal n
        n += 1
        return f"b{n:03d}"

    def heading_path(max_level):
        return [heading_stack[l] for l in sorted(heading_stack) if l <= max_level]

    blocks.append({"block_id": next_id(), "structural_position": "title", "heading_path": [], "text": title_text})
    for el in walk_html(container):
        text = clean_text(el.get_text(" ", strip=True))
        if not text:
            continue
        name = el.name
        if name == "h1":
            continue
        if name in ("h2", "h3", "h4"):
            level = int(name[1])
            for l in list(heading_stack):
                if l >= level:
                    del heading_stack[l]
            heading_stack[level] = text
            blocks.append({"block_id": next_id(), "structural_position": "section_heading",
                            "heading_path": heading_path(level - 1), "text": text})
            continue
        pos = "quotation" if name == "blockquote" else "body"
        blocks.append({"block_id": next_id(), "structural_position": pos,
                        "heading_path": heading_path(4), "text": text})
    return blocks


def extract_pdf_blocks(pdf_bytes, title_hint):
    import fitz  # pymupdf
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    blocks, n = [], 0

    def next_id():
        nonlocal n
        n += 1
        return f"b{n:03d}"

    title_text = title_hint
    blocks.append({"block_id": next_id(), "structural_position": "title", "heading_path": [], "text": title_text})
    for page in doc:
        for b in page.get_text("blocks"):
            text = clean_text(b[4])
            if not text or len(text) < 3:
                continue
            blocks.append({"block_id": next_id(), "structural_position": "body", "heading_path": [], "text": text})
    doc.close()
    return blocks


def build_doc_json(url, blocks, fmt):
    return {
        "source_url": url,
        "fetched_at": datetime.now().astimezone().isoformat(),
        "format": fmt,
        "blocks": blocks,
    }


# ---------------------------------------------------------------------------
# Attribute heuristics (mirrors 01_manifest.py / 04_segment.py)
# ---------------------------------------------------------------------------

def guess_family(url, text, family_flag):
    if family_flag:
        return family_flag
    dom = domain_of(url)
    if dom in COMPANY_DOMAINS:
        return COMPANY_DOMAINS[dom]
    low = (text or "").lower()
    for fam in FAMILIES:
        if fam.lower() in low[:4000]:
            return fam
    return "None"


def guess_genre(url, text, family, genre_flag):
    if genre_flag:
        return genre_flag
    path = urlparse(url).path.lower()
    dom = domain_of(url)
    low = (text or "").lower()
    if dom in COMPANY_DOMAINS:
        return "PRCO"
    if "written-statement" in path or "written-statements" in path:
        return "WMS"
    if "memorandum of understanding" in low or "/mou" in path:
        return "MOU"
    if "/government/news/" in path:
        return "PRGOV"
    if "blog." in dom or "/blog/" in path:
        return "BLOG"
    if "regulation" in low[:2000] or "white paper" in low[:2000]:
        return "REG"
    return "STRAT"


def guess_speaker(url, family, genre):
    dom = domain_of(url)
    if dom in COMPANY_DOMAINS:
        return COMPANY_DOMAINS[dom]
    if genre == "MOU" and family != "None":
        return f"DSIT_and_{family}"
    if genre == "PRCO" and family != "None":
        return family
    if "gds.blog" in dom:
        return "GDS"
    return "DSIT"


def assign_doc_id(doc_date, genre, speaker, title, existing_ids):
    actor = re.sub(r"[^A-Za-z0-9]", "", speaker.split("_")[-1]) or "Unknown"
    slug = slugify(title)
    base = f"{doc_date}_{genre}_{actor}_{slug}"
    doc_id, i = base, 2
    while doc_id in existing_ids:
        doc_id = f"{base}{i}"
        i += 1
    return doc_id


# ---------------------------------------------------------------------------
# Lexicon / term_status / units (same logic as 04_segment.py)
# ---------------------------------------------------------------------------

def load_lexicon():
    lex = yaml.safe_load(LEXICON.read_text(encoding="utf-8"))
    rx = lambda pats: [re.compile(p, re.I) for p in pats]
    return rx(lex["nominal"]), rx(lex["variant_nominal"]), rx(lex["distributive"])


def hits(rxs, text):
    out = []
    for r in rxs:
        out += [m.group(0) for m in r.finditer(text)]
    return out


def sections(blocks):
    secs, cur, cur_head = [], [], "(start)"
    for b in blocks:
        if b["structural_position"] in ("section_heading", "pillar_name"):
            if cur:
                secs.append((cur_head, cur))
            cur_head, cur = b["text"][:120], [b]
        else:
            cur.append(b)
    if cur:
        secs.append((cur_head, cur))
    return secs


def build_units_and_term_status(doc_id, blocks):
    rx_nom, rx_var, rx_dis = load_lexicon()
    full = "\n".join(b["text"] for b in blocks)
    n_nom, n_var, n_dis = hits(rx_nom, full), hits(rx_var, full), hits(rx_dis, full)
    term_status = "present" if n_nom else ("variant" if n_var else "absent")

    doc_units = []
    for si, (head, sblocks) in enumerate(sections(blocks)):
        text = "\n".join(b["text"] for b in sblocks)
        u_nom, u_var, u_dis = hits(rx_nom, text), hits(rx_var, text), hits(rx_dis, text)
        if u_nom or u_var or u_dis:
            doc_units.append({
                "unit_id": f"{doc_id}::s{si:02d}", "doc_id": doc_id, "heading": head,
                "block_ids": [b["block_id"] for b in sblocks], "text": text, "retrieval": "lexicon",
                "hits_nominal": u_nom, "hits_variant": u_var, "hits_distributive": u_dis})
    if not doc_units and len(full) <= 9000:
        doc_units.append({
            "unit_id": f"{doc_id}::full", "doc_id": doc_id, "heading": blocks[0]["text"][:120],
            "block_ids": [b["block_id"] for b in blocks], "text": full, "retrieval": "full_short_doc",
            "hits_nominal": [], "hits_variant": [], "hits_distributive": []})

    counts_row = {"doc_id": doc_id, "n_nominal": len(n_nom), "n_variant": len(n_var),
                  "n_distributive": len(n_dis), "nominal_forms": "; ".join(sorted(set(f.lower() for f in n_nom)))}
    return term_status, doc_units, counts_row


def gds_tier_of(speaker, full_text):
    low = full_text.lower()
    if speaker in ("GDS", "CDDO", "DSIT_and_GDS") or "GDS" in speaker:
        return "T1"
    if re.search(r"\bgds\b|government digital service|\bi\.ai\b|incubator for (artificial intelligence|ai)|ai playbook|service standard", low):
        return "T2"
    return "T3"


# ---------------------------------------------------------------------------
# Manifest / recompute
# ---------------------------------------------------------------------------

def read_manifest():
    with MANIFEST.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f)), f


def next_corpus_version(rows):
    versions = []
    for r in rows:
        try:
            versions.append(int(float(r.get("corpus_version", 1) or 1)))
        except ValueError:
            versions.append(1)
    return (max(versions) if versions else 1) + 1


def append_manifest_row(row):
    rows, _ = read_manifest()
    fieldnames = list(rows[0].keys()) if rows else list(row.keys())
    for k in row:
        if k not in fieldnames:
            fieldnames.append(k)
    rows.append(row)
    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def append_units(doc_units):
    with UNITS.open("a", encoding="utf-8") as f:
        for u in doc_units:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")


def append_term_counts(row, manifest_row):
    exists = TERM_COUNTS.exists()
    fields = ["doc_id", "genre", "speaker", "family", "n_nominal", "n_variant", "n_distributive", "nominal_forms"]
    full_row = {"doc_id": row["doc_id"], "genre": manifest_row["genre"], "speaker": manifest_row["speaker"],
                "family": manifest_row["family"], "n_nominal": row["n_nominal"], "n_variant": row["n_variant"],
                "n_distributive": row["n_distributive"], "nominal_forms": row["nominal_forms"]}
    with TERM_COUNTS.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        w.writerow(full_row)


def rebuild_network_html():
    """Runs 06_network_v0.py and re-embeds the JSON into authorship_family_map.html."""
    subprocess.run([sys.executable, str(ROOT / "scripts" / "06_network_v0.py")],
                    check=True, cwd=str(ROOT))
    data = json.loads((ROOT / "analysis" / "networks" / "intertextual_v0.json").read_text(encoding="utf-8"))
    html = NETWORK_HTML.read_text(encoding="utf-8")
    new_block = "const DATA = " + json.dumps(data, indent=1, ensure_ascii=False) + ";"
    html2, count = re.subn(r"const DATA = \{.*?\n\};", new_block, html, flags=re.S)
    if count == 0:
        raise RuntimeError("could not find 'const DATA = {...};' in authorship_family_map.html")
    NETWORK_HTML.write_text(html2, encoding="utf-8")


def rebuild_all_recompute():
    rebuild_network_html()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def admit_document(url: str, family: str | None, genre: str | None, result: dict, session) -> dict:
    """Post-checklist: the download already resolved in `result['fetched']` →
    extracts, writes to data/text/, appends the row to the manifest and units
    to units.jsonl, and recalculates network + term_counts. Returns a
    report (dict).

    Assumes the checklist has already run (`run_checklist`); this function
    does not re-evaluate admission rules, it only materializes the intake.
    """
    fetched = result["fetched"]
    if not fetched["ok"]:
        return {"ok": False, "error": "Could not download the document (neither direct nor via archive.org)."}

    if fetched["is_pdf"]:
        title = url.rsplit("/", 1)[-1]
        blocks = extract_pdf_blocks(fetched["resp"].content, title)
        fmt = "pdf"
    else:
        blocks = extract_html_blocks(fetched["soup"], fetched["title"])
        title = fetched["title"]
        fmt = "html"

    full_text = "\n".join(b["text"] for b in blocks)
    doc_date = fetched.get("guessed_date") or datetime.now().strftime("%Y-%m-%d")
    family = guess_family(url, full_text, family)
    genre = guess_genre(url, full_text, family, genre)
    speaker = guess_speaker(url, family, genre)

    rows, _ = read_manifest()
    existing_ids = {r["doc_id"] for r in rows}
    doc_id = assign_doc_id(doc_date, genre, speaker, title, existing_ids)

    term_status, doc_units, counts_row = build_units_and_term_status(doc_id, blocks)
    tier = gds_tier_of(speaker, full_text)
    corpus_version = next_corpus_version(rows)

    archive_url = ""
    try:
        arch_url, _ts = wayback_fallback(session, url)
        archive_url = arch_url or ""
    except Exception:  # noqa: BLE001
        pass

    manifest_row = {
        "doc_id": doc_id, "excel_row": "", "date": doc_date, "genre": genre,
        "actor_raw": speaker, "speaker": speaker, "side": "Public", "family": family,
        "gds_tier": tier, "stage": "", "term_status": term_status, "url": url,
        "archive_url": archive_url, "corpus_version": corpus_version, "is_context": False,
        "fetch_status": "ok", "n_blocks": len(blocks), "n_quotes": sum(1 for b in blocks if b["structural_position"] == "quotation"),
        "n_pillars": sum(1 for b in blocks if b["structural_position"] == "pillar_name"),
        "total_chars": len(full_text), "source": "archive_fallback" if fetched["used_archive"] else "direct",
        "gds_tier_source": "auto_provisional",
    }

    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    doc_json = build_doc_json(url, blocks, fmt)
    doc_json["doc_id"] = doc_id
    (TEXT_DIR / f"{doc_id}.json").write_text(json.dumps(doc_json, indent=2, ensure_ascii=False), encoding="utf-8")

    append_manifest_row(manifest_row)
    append_units(doc_units)
    append_term_counts(counts_row, manifest_row)

    report = {
        "ok": True, "doc_id": doc_id, "manifest_row": manifest_row,
        "n_blocks": len(blocks), "n_units": len(doc_units), "corpus_version": corpus_version,
        "coding_pending_cmd": f".venv/bin/python scripts/05_code.py --doc {doc_id}",
    }
    try:
        rebuild_all_recompute()
        report["recompute_ok"] = True
    except Exception as exc:  # noqa: BLE001
        report["recompute_ok"] = False
        report["recompute_error"] = str(exc)
    return report


def print_report(report: dict):
    if not report["ok"]:
        print(report["error"])
        return
    r = report["manifest_row"]
    print(f"\nDocument admitted: {report['doc_id']}")
    print(f"  date={r['date']} genre={r['genre']} speaker={r['speaker']} family={r['family']} "
          f"gds_tier={r['gds_tier']} term_status={r['term_status']}")
    print(f"  corpus_version={report['corpus_version']} · {report['n_blocks']} blocks · "
          f"{report['n_units']} coding units")
    if report["recompute_ok"]:
        print("\nRecalculated: analysis/networks/intertextual_v0.json, authorship_family_map.html "
              "(DATA re-embedded), analysis/queries/term_counts.csv.")
    else:
        print(f"\nWARNING: the network recalculation failed ({report['recompute_error']}). "
              f"The document was still admitted in the manifest and in coding/units.jsonl.")
    print(f"\ncoding pending: {report['coding_pending_cmd']}")


def main():
    ap = argparse.ArgumentParser(description="Incremental intake of a document into the corpus (Phase 7).")
    ap.add_argument("url")
    ap.add_argument("--family", choices=FAMILIES, default=None)
    ap.add_argument("--genre", choices=sorted(GENRES), default=None)
    ap.add_argument("--dry-run", action="store_true", help="only prints the checklist, does not touch disk")
    ap.add_argument("--yes", action="store_true", help="skips interactive confirmation")
    args = ap.parse_args()

    session = requests.Session()
    result = run_checklist(args.url, session)
    print_checklist(args.url, result)

    if args.dry_run:
        return 0

    fails = [r for r in result["rules"] if r["status"] == "fail"]
    if fails and not args.yes:
        print("\nThere are FAILED rules. This document would not normally be admitted.")

    if not args.yes:
        try:
            ans = input("\nApprove the admission of this document? [y/N]: ").strip().lower()
        except EOFError:
            ans = ""
        if ans != "y":
            print("Intake cancelled by user.")
            return 1

    report = admit_document(args.url, args.family, args.genre, result, session)
    print_report(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
