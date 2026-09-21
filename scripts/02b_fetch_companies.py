"""Phase 1 (companies): downloads and extracts structured text from the
announcements of the frontier AI companies (Anthropic, Cohere, OpenAI, Google
DeepMind, ElevenLabs) listed in data/manifest.csv.

Per document it produces:
  - data/raw/<doc_id>.html        (raw HTML, direct source or archive.org snapshot)
  - data/raw/<doc_id>.meta.json   (download metadata)
  - data/text/<doc_id>.json       (structured blocks: title/section_heading/body/quotation)

Extraction strategy (generic, no per-site dependencies):
  1. Content root = <main> if it has >=3 <p>/<li>, otherwise <article>, otherwise <body>.
  2. Title = first <h1> inside the root.
  3. The elements (h1-h4/p/li/blockquote) that follow the <h1> are processed in
     document order, up to the first "boilerplate" heading (Related/Author/Keep
     reading/Similar articles/...) or a second <h1>, at which point it stops
     (everything after that is "related posts" cards, footer, etc.).
  4. Paragraphs/quotes: a <blockquote> (or a paragraph with typographic quotes +
     an attribution verb "said/commented/...") is classified as "quotation"; if a
     "— Name, Title" line follows, it is merged as attribution.
  5. <li> are kept as "body" only if they have >=30 characters (filters nav/tags).
  6. Short paragraphs with no terminal punctuation (bylines, "Share", "Tags", "Listen to
     article 5 minutes"...) are discarded as boilerplate.

Usage:
  .venv/bin/python scripts/02b_fetch_companies.py [--only DOC_ID] [--use-existing-raw]

--use-existing-raw: if data/raw/<doc_id>.html already exists, reuse it instead of
  downloading (for cases where the raw file was manually replaced, e.g. when
  the site had to be rendered with a browser because both the direct download
  and archive.org failed).
"""
import argparse
import csv
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "manifest.csv"
RAW_DIR = ROOT / "data" / "raw"
TEXT_DIR = ROOT / "data" / "text"

COMPANY_HOSTS = ["anthropic.com", "cohere.com", "openai.com", "deepmind.google", "elevenlabs.io"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

TIMEOUT = 20
RETRIES = 2
MIN_BODY_CHARS = 400

BLOCK_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "blockquote"]
HEADING_TAGS = {"h1", "h2", "h3", "h4"}

BOILERPLATE_HEADING = re.compile(
    r"^(related( content| posts| articles)?|similar articles|keep reading|read more|"
    r"read (this|more) next|you (might|may) also like|more (from|stories)|author|share|"
    r"subscribe|newsletter|up next|recommended|explore more|continue reading)$",
    re.I,
)
ATTRIBUTION_LINE = re.compile(r"^[-‐-―]\s*\S")  # starts with -, en/em dash
QUOTE_SPAN = re.compile(r"[“”\"][^“”\"]{20,}[“”\"]")
QUOTE_VERB = re.compile(
    r"\b(said|says|say|commented|comments|comment|added|adds|noted|notes|stated|states)\b",
    re.I,
)
BOILERPLATE_LITERAL = {
    "share", "copied", "tags", "written by", "subscribe", "sign up", "listen",
}


def norm_ws(s):
    return re.sub(r"\s+", " ", s).replace("(opens in a new window)", "").strip()


def is_boilerplate_para(text):
    t = text.strip()
    if not t:
        return True
    low = t.lower()
    if low in BOILERPLATE_LITERAL:
        return True
    if low.startswith("listen"):
        return True
    if re.match(r"^\d+\s*minutes?( read)?$", low):
        return True
    if re.match(r"^[a-z]+\.?\s+\d{1,2},?\s+\d{4}$", low):  # standalone date "Jun 15, 2025"
        return True
    if len(t) < 100 and not re.search(r"[.!?]", t) and not ATTRIBUTION_LINE.match(t):
        return True
    return False


def is_quotation_para(text):
    return bool(QUOTE_SPAN.search(text) and QUOTE_VERB.search(text))


def _quote_still_open(text):
    """True if `text` ends inside an unclosed quotation.

    AP-style multi-paragraph quotes re-open a fresh curly “ at the start of every
    paragraph but only close with ” on the final one, so a naive even/odd count of
    quote marks does not work (open marks keep piling up). Directional curly quotes
    let us just compare the position of the last opener to the last closer.
    """
    last_open = text.rfind("“")  # “
    last_close = text.rfind("”")  # ”
    if last_open == -1 and last_close == -1:
        # No curly quotes -- fall back to parity on plain double quotes, if any.
        return text.count('"') % 2 == 1
    return last_open > last_close


class _Elem:
    """Lightweight (name, text) node so merged multi-paragraph quotations can be
    fed through the same block-building loop as real bs4 tags."""

    __slots__ = ("name", "text", "tag")

    def __init__(self, name, text, tag=None):
        self.name = name
        self.text = text
        self.tag = tag

    def get_text(self, *_a, **_kw):
        return self.text

    def find_all(self, *a, **kw):
        return self.tag.find_all(*a, **kw) if self.tag is not None else []


def merge_dangling_quotes(elements):
    """Press releases often split a single attributed quotation across several
    <p> tags (AP style: each paragraph of a multi-para quote opens a new curly
    quote, only the last one closes it). Detect a paragraph that ends with an
    unmatched opening quote mark and merge it with the following paragraph(s)
    until the quote closes, so the combined text can be classified as one
    "quotation" block instead of leaking through as unattributed "body" text.
    """
    out = []
    i = 0
    n = len(elements)
    while i < n:
        el = elements[i]
        if el.name != "p":
            out.append(_Elem(el.name, norm_ws(el.get_text(" ", strip=True)), el))
            i += 1
            continue
        text = norm_ws(el.get_text(" ", strip=True))
        j = i
        combined = text
        combined_tag = el
        # Only attempt the merge when this paragraph carries an attribution verb
        # (e.g. "X said, “...") -- otherwise an unrelated stray/unbalanced quote
        # mark (a typo, a scare-quoted word) could wrongly glue paragraphs together.
        can_merge = bool(QUOTE_VERB.search(text))
        merges = 0
        while (
            can_merge
            and _quote_still_open(combined)
            and j + 1 < n
            and elements[j + 1].name == "p"
            and merges < 4  # safety cap against a runaway merge if quotes never balance
        ):
            j += 1
            merges += 1
            nxt = norm_ws(elements[j].get_text(" ", strip=True))
            combined = f"{combined} {nxt}"
            combined_tag = None  # merged node no longer maps to a single source tag
        if j > i:
            out.append(_Elem("p", combined, combined_tag))
        else:
            out.append(_Elem("p", text, el))
        i = j + 1
    return out


def pick_content_root(soup):
    main = soup.find("main")
    if main and len(main.find_all(["p", "li"])) >= 3:
        return main
    article = soup.find("article")
    if article and len(article.find_all(["p", "li"])) >= 3:
        return article
    return soup.body or soup


def extract_blocks(html_bytes):
    """Returns (title, blocks) from raw HTML bytes."""
    soup = BeautifulSoup(html_bytes, "lxml")
    root = pick_content_root(soup)
    all_els = root.find_all(BLOCK_TAGS)

    h1_idx = next((i for i, e in enumerate(all_els) if e.name == "h1"), None)
    if h1_idx is None:
        h1 = soup.find("h1")
        title = norm_ws(h1.get_text(" ", strip=True)) if h1 else None
        elements = merge_dangling_quotes(all_els)
    else:
        title = norm_ws(all_els[h1_idx].get_text(" ", strip=True))
        elements = merge_dangling_quotes(all_els[h1_idx + 1 :])

    # Text of every heading in the doc, used to drop table-of-contents <li>/<p>
    # entries that merely repeat a heading (anchor-jump nav widgets).
    heading_texts = {norm_ws(h.get_text(" ", strip=True)) for h in root.find_all(["h1", "h2", "h3", "h4"])}

    # Persistent widgets (CTA banners, promo taglines) tend to appear verbatim more
    # than once on the page; genuine article prose essentially never repeats itself
    # word-for-word. Flag short paragraphs that recur so they can be dropped.
    para_counts = {}
    for e in root.find_all(["p", "li"]):
        t = norm_ws(e.get_text(" ", strip=True))
        if t:
            para_counts[t] = para_counts.get(t, 0) + 1
    repeated_short_texts = {t for t, c in para_counts.items() if c >= 2 and len(t) < 150}

    blocks = []
    heading_stack = []  # list of (level, text)
    n = 1

    def next_id():
        nonlocal n
        bid = f"b{n:03d}"
        n += 1
        return bid

    if title:
        blocks.append({
            "block_id": next_id(),
            "structural_position": "title",
            "heading_path": [],
            "text": title,
        })

    i = 0
    while i < len(elements):
        el = elements[i]
        tag = el.name
        text = norm_ws(el.get_text(" ", strip=True))

        if tag in HEADING_TAGS:
            if tag == "h1" or BOILERPLATE_HEADING.match(text):
                break  # everything past this point is boilerplate / unrelated content
            level = int(tag[1])
            heading_stack = [h for h in heading_stack if h[0] < level]
            heading_stack.append((level, text))
            if text:
                blocks.append({
                    "block_id": next_id(),
                    "structural_position": "section_heading",
                    "heading_path": [h[1] for h in heading_stack[:-1]],
                    "text": text,
                })
            i += 1
            continue

        if tag == "blockquote":
            quote_text = text
            j = i + 1
            if j < len(elements) and elements[j].name == "p":
                dup = norm_ws(elements[j].get_text(" ", strip=True))
                if dup == quote_text:
                    j += 1
            if j < len(elements) and elements[j].name == "p":
                attr = norm_ws(elements[j].get_text(" ", strip=True))
                if ATTRIBUTION_LINE.match(attr):
                    quote_text = f"{quote_text} {attr}"
                    j += 1
            if quote_text:
                blocks.append({
                    "block_id": next_id(),
                    "structural_position": "quotation",
                    "heading_path": [h[1] for h in heading_stack],
                    "text": quote_text,
                })
            i = j
            continue

        if tag == "li":
            if len(text) >= 30 and text not in heading_texts and text not in repeated_short_texts:
                blocks.append({
                    "block_id": next_id(),
                    "structural_position": "body",
                    "heading_path": [h[1] for h in heading_stack],
                    "text": text,
                })
            i += 1
            continue

        if tag == "p":
            # Some CMSes (e.g. Cohere's Ghost blog) style in-article subheadings as a
            # bare <p><strong>...</strong></p> instead of a real <h2>-<h4>. Treat a
            # short bold-only paragraph as a pseudo section_heading.
            strong_children = [c for c in el.find_all(["strong", "b"], recursive=False)]
            if (
                len(strong_children) == 1
                and norm_ws(strong_children[0].get_text(" ", strip=True)) == text
                and text
                and len(text) < 100
                and not re.search(r"[.!?]$", text)
            ):
                level = 3
                heading_stack = [h for h in heading_stack if h[0] < level]
                heading_stack.append((level, text))
                blocks.append({
                    "block_id": next_id(),
                    "structural_position": "section_heading",
                    "heading_path": [h[1] for h in heading_stack[:-1]],
                    "text": text,
                })
                i += 1
                continue
            if ATTRIBUTION_LINE.match(text):
                if blocks and blocks[-1]["structural_position"] == "quotation":
                    blocks[-1]["text"] = f"{blocks[-1]['text']} {text}"
                i += 1
                continue
            if is_boilerplate_para(text) or text in heading_texts or text in repeated_short_texts:
                i += 1
                continue
            pos = "quotation" if is_quotation_para(text) else "body"
            blocks.append({
                "block_id": next_id(),
                "structural_position": pos,
                "heading_path": [h[1] for h in heading_stack],
                "text": text,
            })
            i += 1
            continue

        i += 1

    return title, blocks


def body_chars(blocks):
    return sum(len(b["text"]) for b in blocks if b["structural_position"] in ("body", "quotation"))


def fetch(url, timeout=TIMEOUT, retries=RETRIES, headers=None):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=headers or HEADERS, timeout=timeout, allow_redirects=True)
            return r
        except requests.RequestException as e:
            last_exc = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise last_exc


def load_company_rows():
    with MANIFEST.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        host = urlparse(row["url"]).netloc.replace("www.", "")
        if any(h in host for h in COMPANY_HOSTS):
            out.append(row)
    return out


def process_doc(row, use_existing_raw=False):
    doc_id = row["doc_id"]
    url = row["url"]
    raw_path = RAW_DIR / f"{doc_id}.html"
    meta_path = RAW_DIR / f"{doc_id}.meta.json"
    text_path = TEXT_DIR / f"{doc_id}.json"

    fetched_at = datetime.now(timezone.utc).isoformat()
    source = None
    http_status = None
    content_type = None
    final_url = url
    error = None
    html_bytes = None

    if use_existing_raw and raw_path.exists():
        html_bytes = raw_path.read_bytes()
        source = "direct"
        http_status = 200
        content_type = "text/html"
        print(f"  [{doc_id}] using existing raw file on disk ({len(html_bytes)} bytes)")
    else:
        try:
            r = fetch(url)
            http_status = r.status_code
            content_type = r.headers.get("content-type")
            final_url = r.url
            blocked = r.status_code in (403, 429, 503) or r.status_code >= 500
            if not blocked and r.status_code == 200:
                title, blocks = extract_blocks(r.content)
                if title and body_chars(blocks) >= MIN_BODY_CHARS:
                    html_bytes = r.content
                    source = "direct"
                else:
                    error = (
                        f"direct fetch 200 but insufficient body "
                        f"(title={bool(title)}, body_chars={body_chars(blocks)}) -> trying archive.org"
                    )
            else:
                error = f"direct fetch blocked/erroneous (status={r.status_code}) -> trying archive.org"
        except requests.RequestException as e:
            error = f"direct fetch exception: {e} -> trying archive.org"

        if html_bytes is None:
            archive_url = f"https://web.archive.org/web/2/{url}"
            try:
                r2 = fetch(archive_url, timeout=30)
                if r2.status_code == 200:
                    title, blocks = extract_blocks(r2.content)
                    if title and body_chars(blocks) >= MIN_BODY_CHARS:
                        html_bytes = r2.content
                        source = "archive_org"
                        http_status = r2.status_code
                        content_type = r2.headers.get("content-type")
                        final_url = r2.url
                        error = None
                    else:
                        error = (
                            (error or "")
                            + f" | archive.org 200 but insufficient body (body_chars={body_chars(blocks)})"
                        )
                else:
                    error = (error or "") + f" | archive.org status={r2.status_code}"
                    http_status = r2.status_code
            except requests.RequestException as e:
                error = (error or "") + f" | archive.org exception: {e}"

        # Tier 3: some sites (Cohere, Ghost/Next.js RSC blogs) stream the article body
        # as client-side JS with no server-rendered <p>/<li> content in the raw HTML nor
        # in the Wayback capture (which is fetched the same non-JS way). As a last resort,
        # render through r.jina.ai (a JS-rendering readability proxy) against the *direct*
        # source URL -- still the direct document, just fetched via a renderer instead of
        # a bare HTTP GET, so it is recorded as source="direct".
        if html_bytes is None:
            reader_url = f"https://r.jina.ai/{url}"
            try:
                r3 = fetch(reader_url, timeout=45, headers={
                    # r.jina.ai (Cloudflare-fronted) issues a JS challenge to a
                    # full desktop-Chrome UA string; a plain/generic UA sails through.
                    "User-Agent": "Mozilla/5.0",
                    "X-Return-Format": "html",
                })
                if r3.status_code == 200:
                    title, blocks = extract_blocks(r3.content)
                    if title and body_chars(blocks) >= MIN_BODY_CHARS:
                        html_bytes = r3.content
                        source = "direct"
                        http_status = r3.status_code
                        content_type = "text/html"
                        final_url = url
                        error = (error or "") + " | resolved via JS rendering (r.jina.ai) on the direct URL"
                    else:
                        error = (
                            (error or "")
                            + f" | r.jina.ai 200 but insufficient body (body_chars={body_chars(blocks)})"
                        )
                else:
                    error = (error or "") + f" | r.jina.ai status={r3.status_code}"
            except requests.RequestException as e:
                error = (error or "") + f" | r.jina.ai exception: {e}"

    if html_bytes is None:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        meta = {
            "doc_id": doc_id,
            "fetch_status": "failed",
            "http_status": http_status,
            "content_type": content_type,
            "final_url": final_url,
            "source": source,
            "sha256": None,
            "bytes": None,
            "n_blocks": 0,
            "error": error,
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  [{doc_id}] FAILED: {error}")
        return meta

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(html_bytes)

    title, blocks = extract_blocks(html_bytes)
    doc = {
        "doc_id": doc_id,
        "source_url": url,
        "fetched_at": fetched_at,
        "format": "html",
        "blocks": blocks,
    }
    text_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    sha256 = hashlib.sha256(html_bytes).hexdigest()
    meta = {
        "doc_id": doc_id,
        "fetch_status": "ok",
        "http_status": http_status,
        "content_type": content_type,
        "final_url": final_url,
        "source": source,
        "sha256": sha256,
        "bytes": len(html_bytes),
        "n_blocks": len(blocks),
        "error": error,
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    n_titles = sum(1 for b in blocks if b["structural_position"] == "title")
    bc = body_chars(blocks)
    flags = []
    if n_titles != 1:
        flags.append(f"n_titles={n_titles} (expected 1)")
    if bc < MIN_BODY_CHARS:
        flags.append(f"body_chars={bc} < {MIN_BODY_CHARS}")
    flag_str = f" -- REVIEW: {'; '.join(flags)}" if flags else ""
    print(f"  [{doc_id}] ok source={source} n_blocks={len(blocks)} body_chars={bc} title={title!r}{flag_str}")
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="process only this doc_id")
    ap.add_argument("--use-existing-raw", action="store_true",
                     help="if data/raw/<doc_id>.html already exists, reuse it instead of downloading")
    args = ap.parse_args()

    rows = load_company_rows()
    if args.only:
        rows = [r for r in rows if r["doc_id"] == args.only]
        if not rows:
            print(f"doc_id not found among company rows: {args.only}")
            return 1

    print(f"Company documents to process: {len(rows)}")
    results = []
    for row in rows:
        meta = process_doc(row, use_existing_raw=args.use_existing_raw)
        results.append(meta)

    print("\nSummary:")
    for m in results:
        print(f"  {m['doc_id']}: fetch_status={m['fetch_status']} source={m['source']} n_blocks={m['n_blocks']}")
    n_ok = sum(1 for m in results if m["fetch_status"] == "ok")
    print(f"\n{n_ok}/{len(results)} documents OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
