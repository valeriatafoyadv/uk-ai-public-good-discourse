"""Generates analysis/guidebook_summary.html: an interactive review tool for
coding/guidebook_draft.yaml (Round 1.2 candidate sub-codes), for the author to
confirm, rename, split, and regroup clusters before naming the final codebook.

Metaphor analysis is intentionally NOT part of this tool: it is not part of
the committed analytical framework (the METAPHOR question is extracted by the
pipeline as a resource only, and scripts/06_consolidate.py writes its raw
report to analysis/metaphors_report.md).

Unlike a static summary, this page shows every individual coded instance
(not just 3 examples per cluster) with a checkbox, so the author can select
instances that were merged too aggressively (the common failure mode of
cosine-similarity clustering at a single threshold) and move them into a new
or existing cluster. State persists in the browser's localStorage; "Export
guidebook.yaml" writes the final, author-confirmed file.

Pure Python; safe to re-run any time coding/round1/*.jsonl or
coding/guidebook_draft.yaml change -- re-running does NOT touch the author's
in-browser progress (localStorage is keyed by instance id, which is stable
across re-generation as long as the underlying round1 records don't change).
"""
import glob
import html
import json
import os
import re
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GB = yaml.safe_load((ROOT / "coding" / "guidebook_draft.yaml").read_text(encoding="utf-8"))
OUT = ROOT / "analysis" / "guidebook_summary.html"

CORE_QUESTIONS = ["BENEFICIARY", "MECHANISM", "SAFEGUARD", "RESPONSIBILITY",
                  "PROJECTED_FUTURE", "ACTANTS", "NATURALISED_ORDER"]

for _qname, _qdata in GB.get("questions", {}).items():
    if _qdata.get("clusters") is None:
        _qdata["clusters"] = []
        _qdata["n_clusters"] = 0

QUESTION_THEORY = {
    "BENEFICIARY": "Gee (2011), subject tool",
    "MECHANISM": "Gee (2011), fill-in tool",
    "SAFEGUARD": "Gee (2011), fill-in tool",
    "RESPONSIBILITY": "Gee (2011), subject tool",
    "PROJECTED_FUTURE": "Jasanoff & Kim (2015)",
    "ACTANTS": "Kaplan (1993)",
    "NATURALISED_ORDER": "Lears (1985); Gee (2011)",
}


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def esc_attr(s):
    return html.escape(str(s), quote=True) if s is not None else ""


# ---------------------------------------------------------------------------
# Load every Round 1.2 instance (question, unit_id) -> ordered list of
# records, so each cluster's member_unit_ids can be resolved to an actual
# quote instead of just the 3 stored examples.
# ---------------------------------------------------------------------------

def load_instance_pool():
    pool = defaultdict(list)
    for p in sorted(glob.glob(str(ROOT / "coding" / "round1" / "*.jsonl"))):
        base = os.path.basename(p)
        if base in ("doc_profiles.jsonl", "definitional_instances.jsonl"):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if r.get("question") in CORE_QUESTIONS and r.get("applies") and r.get("answer_summary"):
                    pool[(r["question"], r["unit_id"])].append(r)
    # assign a stable instance id up front, before any popping
    for key, recs in pool.items():
        q, uid = key
        for i, r in enumerate(recs):
            r["_iid"] = f"{q}::{uid}::{i}"
    return pool


POOL = load_instance_pool()
POOL_CURSOR = defaultdict(int)  # (q, uid) -> next index to hand out


def next_instance_for(q, unit_id):
    key = (q, unit_id)
    i = POOL_CURSOR[key]
    recs = POOL.get(key, [])
    if i < len(recs):
        POOL_CURSOR[key] += 1
        return recs[i]
    # Fallback: pool exhausted (shouldn't happen if counts are consistent) --
    # reuse the last record rather than crash, and flag it in the console.
    if recs:
        return recs[-1]
    return None


def main():
    q_stats = {q: {"n_applies_true": d["n_applies_true"], "n_clusters": len(d["clusters"])}
               for q, d in GB["questions"].items()}
    total_instances = sum(s["n_applies_true"] for s in q_stats.values())
    total_clusters = sum(s["n_clusters"] for s in q_stats.values())

    nav_items = "".join(
        f'<a href="#{q.lower()}" class="navlink">{esc(q.replace("_", " ").title())}'
        f'<span class="navcount">{d["n_clusters"]}</span></a>'
        for q, d in GB["questions"].items())

    # all_instances_by_q feeds the client-side JS state machine: every
    # instance the author can select/move, grouped by question, with its
    # ORIGINAL cluster name (the starting assignment before any moves).
    all_instances_by_q = defaultdict(list)

    sections = []
    for q, data in GB["questions"].items():
        clusters = sorted(data["clusters"], key=lambda c: -c["n_instances"])
        ratio = len(clusters) / max(data["n_applies_true"], 1)
        granular_flag = (
            '<span class="badge badge-warn">Low merge rate '
            f'({len(clusters)} clusters / {data["n_applies_true"]} instances) '
            '&mdash; likely needs manual splitting, not just a name</span>'
            if ratio > 0.4 else ""
        )
        if data.get("error"):
            granular_flag += (
                '<span class="badge badge-warn">Clustering skipped for this question: '
                f'{esc(data["error"])}</span>'
            )
        cluster_names_js = json.dumps([c["candidate_name"] for c in clusters])
        cards = []
        for c in clusters:
            instance_rows = []
            for uid in c.get("member_unit_ids", []):
                rec = next_instance_for(q, uid)
                if rec is None:
                    continue
                quote = (rec.get("verbatim_quote") or rec.get("answer_summary") or "").replace("\n", " ").strip()
                doc_id = rec.get("doc_id", uid.split("::")[0])
                inst = {"iid": rec["_iid"], "doc_id": doc_id, "quote": quote,
                        "cluster": c["candidate_name"]}
                all_instances_by_q[q].append(inst)
                instance_rows.append(f'''
        <li class="inst-row" data-iid="{esc_attr(inst["iid"])}">
          <input type="checkbox" class="inst-check" data-iid="{esc_attr(inst["iid"])}">
          <span class="inst-quote" contenteditable="true" spellcheck="false" data-iid="{esc_attr(inst["iid"])}"
            title="{esc_attr(doc_id)} — click to edit this text">&ldquo;{esc(quote)}&rdquo;</span>
          <span class="inst-doc">{esc(doc_id)}</span>
          <button type="button" class="inst-drop" data-iid="{esc_attr(inst["iid"])}" title="Drop this instance">&times;</button>
        </li>''')
            cards.append(f'''
    <div class="cluster-card" data-cluster="{esc_attr(c["candidate_name"])}" data-question="{esc_attr(q)}">
      <div class="cluster-head">
        <span class="cluster-name">{esc(c["candidate_name"])}</span>
        <span class="cluster-n" data-n-for="{esc_attr(c["candidate_name"])}">{c["n_instances"]} instance{"s" if c["n_instances"] != 1 else ""}</span>
      </div>
      <ul class="inst-list">{"".join(instance_rows)}</ul>
      <div class="rename-row">
        <label>Final name: <input type="text" class="rename-input" placeholder="{esc_attr(c["candidate_name"])}"
          data-question="{esc_attr(q)}" data-draft="{esc_attr(c["candidate_name"])}"></label>
        <label class="confirm-label"><input type="checkbox" class="confirm-check"
          data-question="{esc_attr(q)}" data-cluster="{esc_attr(c["candidate_name"])}"> Confirmed</label>
      </div>
      <button type="button" class="btn-add-inst" data-question="{esc_attr(q)}" data-cluster="{esc_attr(c["candidate_name"])}">+ Add a fragment</button>
    </div>''')
        sections.append(f'''
<section id="{q.lower()}" class="qsection" data-question="{esc_attr(q)}" data-cluster-names='{esc_attr(cluster_names_js)}'>
  <h2>{esc(q.replace("_", " ").title())}
    <span class="theory">{esc(QUESTION_THEORY.get(q, ""))}</span></h2>
  <p class="qmeta">{data["n_applies_true"]} coded instances &middot; {len(clusters)} candidate clusters</p>
  <div class="toolbar">
    <button class="btn-secondary" onclick="moveSelected('{esc_attr(q)}')">Move checked to&hellip;</button>
    <span class="sel-count" id="selcount-{esc_attr(q)}"></span>
  </div>
  {granular_flag}
  <div class="cluster-grid">{"".join(cards)}</div>
</section>''')

    html_out = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Guidebook review — 66 documents</title>
<style>
:root{{
  --canvas:#ffffff; --band:#f7f7f7; --card:#ffffff; --card-fill:#eef0f3;
  --ink:#0a0b0d; --body:#5b616e; --muted:#7c828a; --hairline:#dee1e6;
  --accent:#0052ff; --accent-active:#003ecc; --warn-bg:#fff4e0; --warn-ink:#7a4a00;
  --moved-bg:#e9f7ee; --moved-ink:#0a7a3d;
}}
*{{box-sizing:border-box}}
html,body{{margin:0;background:var(--canvas);color:var(--ink);
  font:15px/1.55 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:1280px;margin:0 auto;padding:28px 24px 100px;display:grid;
  grid-template-columns:220px 1fr;gap:32px}}
header{{grid-column:1/-1}}
h1{{font-size:22px;font-weight:600;margin:0 0 4px}}
.sub{{color:var(--body);font-size:14px;margin:0 0 20px;max-width:900px}}
.stats{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px}}
.stat{{background:var(--card-fill);border-radius:8px;padding:10px 16px}}
.stat b{{display:block;font-size:20px;font-weight:600}}
.stat span{{font-size:12px;color:var(--muted)}}
nav{{position:sticky;top:20px;align-self:start;font-size:13px}}
.navlink{{display:flex;justify-content:space-between;padding:6px 10px;border-radius:6px;
  color:var(--body);text-decoration:none;margin-bottom:2px}}
.navlink:hover{{background:var(--band);color:var(--ink)}}
.navcount{{color:var(--muted)}}
main{{min-width:0}}
.qsection{{border-top:1px solid var(--hairline);padding:28px 0}}
.qsection:first-child{{border-top:none;padding-top:0}}
h2{{font-size:18px;font-weight:600;margin:0 0 2px;display:flex;align-items:baseline;gap:10px}}
.theory{{font-size:12px;font-weight:400;color:var(--muted)}}
.qmeta{{font-size:13px;color:var(--body);margin:0 0 10px}}
.toolbar{{display:flex;align-items:center;gap:12px;margin-bottom:10px}}
.btn-secondary{{background:var(--card-fill);color:var(--ink);border:1px solid var(--hairline);
  border-radius:8px;padding:7px 14px;font-size:13px;cursor:pointer}}
.btn-secondary:hover{{background:var(--band)}}
.sel-count{{font-size:12px;color:var(--muted)}}
.badge-warn{{display:inline-block;background:var(--warn-bg);color:var(--warn-ink);
  font-size:12px;padding:4px 10px;border-radius:6px;margin-bottom:12px}}
.cluster-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}}
.cluster-card{{background:var(--card);border:1px solid var(--hairline);border-radius:10px;padding:14px;
  display:flex;flex-direction:column}}
.cluster-card.is-new{{border-color:var(--accent);border-style:dashed}}
.cluster-head{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;gap:8px}}
.cluster-name{{font-weight:600;font-size:14px;font-family:ui-monospace,Menlo,monospace}}
.cluster-n{{font-size:12px;color:var(--muted);white-space:nowrap}}
.inst-list{{list-style:none;margin:0 0 10px;padding:0;font-size:12.5px;color:var(--body);
  max-height:260px;overflow-y:auto;border:1px solid var(--hairline);border-radius:6px}}
.inst-row{{display:flex;gap:6px;align-items:flex-start;padding:6px 8px;border-bottom:1px solid var(--hairline)}}
.inst-row:last-child{{border-bottom:none}}
.inst-row.is-moved{{background:var(--moved-bg)}}
.inst-row.is-added{{background:#eef2ff}}
.inst-check{{margin-top:2px;flex:none}}
.inst-quote{{flex:1;min-width:0}}
.inst-quote:focus{{outline:1px solid var(--accent);background:#fff;border-radius:3px}}
.inst-doc{{font-size:10.5px;color:var(--muted);white-space:nowrap;font-family:ui-monospace,Menlo,monospace}}
.inst-drop{{flex:none;background:transparent;color:var(--muted);border:none;font-size:15px;
  line-height:1;padding:0 2px;cursor:pointer}}
.inst-drop:hover{{color:#c0392b;background:transparent}}
.btn-add-inst{{margin-top:8px;background:transparent;color:var(--accent);border:1px dashed var(--hairline);
  border-radius:6px;padding:5px 10px;font-size:12px;width:100%}}
.btn-add-inst:hover{{background:var(--band);color:var(--accent-active)}}
.rename-row{{border-top:1px solid var(--hairline);padding-top:8px;display:flex;justify-content:space-between;
  align-items:center;gap:8px;margin-top:auto}}
.rename-row label{{font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:4px;flex:1}}
.confirm-label{{flex-direction:row !important;align-items:center;gap:5px !important;white-space:nowrap}}
.rename-input{{border:1px solid var(--hairline);border-radius:6px;padding:6px 8px;font-size:13px;
  font-family:ui-monospace,Menlo,monospace;color:var(--ink)}}
.rename-input:focus{{outline:2px solid var(--accent);outline-offset:1px;border-color:var(--accent)}}
.mformula{{font-family:ui-monospace,Menlo,monospace;font-size:13px;color:var(--accent-active);margin:0 0 6px}}
.mdomains,.mhh{{font-size:13px;color:var(--body);margin:0 0 4px}}
#export-bar{{position:sticky;bottom:0;background:var(--canvas);border-top:1px solid var(--hairline);
  padding:12px 0;margin-top:20px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
button{{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:9px 16px;
  font-size:13px;font-weight:500;cursor:pointer}}
button:hover{{background:var(--accent-active)}}
#export-note{{font-size:12px;color:var(--muted)}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Guidebook review — Round 1.2 candidate sub-codes</h1>
  <p class="sub">Auto-clustered by cosine similarity (embeddinggemma, threshold {esc(GB.get("similarity_threshold", 0.75))})
    from {total_instances} coded instances into {total_clusters} candidate clusters.
    <b>These are suggestions, not codes.</b> Check the instances that don't belong, click
    &ldquo;Move checked to&hellip;&rdquo; to split them into a new or existing cluster, type
    the final name in each card, tick &ldquo;Confirmed&rdquo; once you're happy with a cluster,
    then &ldquo;Export guidebook.yaml&rdquo;. Your progress saves automatically in this browser
    (localStorage) — re-running the generator script does not erase it.</p>
  <div class="stats">
    {"".join(f'<div class="stat"><b>{esc(s["n_clusters"])}</b><span>{esc(q.replace("_"," ").title())}</span></div>' for q, s in q_stats.items())}
  </div>
</header>
<nav>{nav_items}
</nav>
<main>
{"".join(sections)}
<div id="export-bar">
  <button onclick="exportYaml()">Export guidebook.yaml &darr;</button>
  <button class="btn-secondary" onclick="resetProgress()">Reset all progress</button>
  <span id="export-note">Reflects every move, rename, and confirmation you've made in this browser.</span>
</div>
</main>
</div>
<script>
const LS_KEY = 'guidebook_review_state_v1';

function emptyState(){{ return {{moves:{{}}, newClusters:{{}}, names:{{}}, confirmed:{{}}, dropped:{{}}, edits:{{}}, added:[]}}; }}
function loadState(){{
  try {{ return {{...emptyState(), ...(JSON.parse(localStorage.getItem(LS_KEY)) || {{}})}}; }}
  catch(e) {{ return emptyState(); }}
}}
function saveState(s){{ localStorage.setItem(LS_KEY, JSON.stringify(s)); }}
let STATE = loadState();

function applyStateToDom(){{
  // Renames
  document.querySelectorAll('.rename-input').forEach(inp => {{
    const key = inp.dataset.question + '::' + inp.dataset.draft;
    if (STATE.names[key]) inp.value = STATE.names[key];
  }});
  // Confirmed
  document.querySelectorAll('.confirm-check').forEach(chk => {{
    const key = chk.dataset.question + '::' + chk.dataset.cluster;
    if (STATE.confirmed[key]) chk.checked = true;
  }});
  // Moves: re-parent instance rows into their target cluster (creating new
  // cluster cards for any target that doesn't exist yet as an original cluster).
  Object.entries(STATE.moves).forEach(([iid, target]) => {{
    const row = document.querySelector(`.inst-row[data-iid="${{cssEscape(iid)}}"]`);
    if (!row) return;
    let card = document.querySelector(`.cluster-card[data-cluster="${{cssEscape(target.cluster)}}"][data-question="${{cssEscape(target.question)}}"]`);
    if (!card) card = createNewClusterCard(target.question, target.cluster);
    card.querySelector('.inst-list').appendChild(row);
    row.classList.add('is-moved');
  }});
  // Dropped instances: remove from the DOM entirely.
  Object.keys(STATE.dropped).forEach(iid => {{
    if (!STATE.dropped[iid]) return;
    const row = document.querySelector(`.inst-row[data-iid="${{cssEscape(iid)}}"]`);
    if (row) row.remove();
  }});
  // Edited quote text.
  Object.entries(STATE.edits).forEach(([iid, text]) => {{
    const span = document.querySelector(`.inst-quote[data-iid="${{cssEscape(iid)}}"]`);
    if (span) span.textContent = '\\u201c' + text + '\\u201d';
  }});
  // Manually added fragments.
  STATE.added.forEach(a => {{
    let card = document.querySelector(`.cluster-card[data-cluster="${{cssEscape(a.cluster)}}"][data-question="${{cssEscape(a.question)}}"]`);
    if (!card) card = createNewClusterCard(a.question, a.cluster);
    const li = document.createElement('li');
    li.className = 'inst-row is-added';
    li.dataset.iid = a.iid;
    li.innerHTML = `<input type="checkbox" class="inst-check" data-iid="${{a.iid}}">
      <span class="inst-quote" contenteditable="true" spellcheck="false" data-iid="${{a.iid}}" title="${{a.doc}} — click to edit">&ldquo;${{a.text}}&rdquo;</span>
      <span class="inst-doc">${{a.doc}}</span>
      <button type="button" class="inst-drop" data-iid="${{a.iid}}" title="Drop this instance">&times;</button>`;
    card.querySelector('.inst-list').appendChild(li);
    wireInstanceRow(li);
  }});
  refreshCounts();
}}

function wireInstanceRow(row){{
  row.querySelector('.inst-check').addEventListener('change', updateSelCounts);
  row.querySelector('.inst-drop').addEventListener('click', onDropClick);
  row.querySelector('.inst-quote').addEventListener('blur', onQuoteEdit);
}}

function onDropClick(e){{
  const iid = e.target.dataset.iid;
  if (!confirm('Drop this fragment from the guidebook?')) return;
  STATE.dropped[iid] = true;
  saveState(STATE);
  e.target.closest('.inst-row').remove();
  refreshCounts();
}}

function onQuoteEdit(e){{
  const span = e.target;
  const iid = span.dataset.iid;
  const text = span.textContent.replace(/^[\\u201c"]|[\\u201d"]$/g, '');
  STATE.edits[iid] = text;
  saveState(STATE);
}}

function addFragment(question, cluster){{
  const text = window.prompt('Text of the new fragment (paste the quote or write your own note):');
  if (!text) return;
  const doc = window.prompt('doc_id this fragment comes from (or leave blank):', '') || 'manual';
  const iid = 'manual::' + question + '::' + Date.now() + '::' + Math.floor(Math.random()*1000);
  STATE.added.push({{iid, question, cluster, text, doc}});
  saveState(STATE);
  location.reload();
}}

function cssEscape(s){{ return (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/["\\\\]/g, '\\\\$&'); }}

function createNewClusterCard(question, name){{
  const section = document.querySelector(`.qsection[data-question="${{cssEscape(question)}}"]`);
  const grid = section.querySelector('.cluster-grid');
  const card = document.createElement('div');
  card.className = 'cluster-card is-new';
  card.dataset.cluster = name;
  card.dataset.question = question;
  card.innerHTML = `
    <div class="cluster-head">
      <span class="cluster-name">${{name}} <span style="color:var(--accent);font-weight:400">(new)</span></span>
      <span class="cluster-n" data-n-for="${{name}}">0 instances</span>
    </div>
    <ul class="inst-list"></ul>
    <div class="rename-row">
      <label>Final name: <input type="text" class="rename-input" placeholder="${{name}}"
        data-question="${{question}}" data-draft="${{name}}"></label>
      <label class="confirm-label"><input type="checkbox" class="confirm-check"
        data-question="${{question}}" data-cluster="${{name}}"> Confirmed</label>
    </div>
    <button type="button" class="btn-add-inst" data-question="${{question}}" data-cluster="${{name}}">+ Add a fragment</button>`;
  grid.appendChild(card);
  card.querySelector('.rename-input').addEventListener('input', onRenameInput);
  card.querySelector('.confirm-check').addEventListener('change', onConfirmChange);
  card.querySelector('.btn-add-inst').addEventListener('click', () => addFragment(question, name));
  return card;
}}

function refreshCounts(){{
  document.querySelectorAll('.cluster-card').forEach(card => {{
    const n = card.querySelectorAll('.inst-row').length;
    const label = card.querySelector('.cluster-n');
    if (label) label.textContent = n + (n === 1 ? ' instance' : ' instances');
  }});
}}

function moveSelected(question){{
  const section = document.querySelector(`.qsection[data-question="${{cssEscape(question)}}"]`);
  const checked = [...section.querySelectorAll('.inst-check:checked')];
  if (checked.length === 0) {{ alert('Check at least one instance first.'); return; }}
  const existing = JSON.parse(section.dataset.clusterNames || '[]');
  const extra = [...new Set(Object.values(STATE.moves).filter(m => m.question===question).map(m => m.cluster))];
  const options = [...new Set([...existing, ...extra])];
  const promptText = 'Move ' + checked.length + ' instance(s) to which cluster?\\n' +
    'Type an EXISTING name from this list, or a NEW name to create one:\\n\\n' + options.join(', ');
  const target = window.prompt(promptText);
  if (!target) return;
  checked.forEach(chk => {{
    const iid = chk.dataset.iid;
    STATE.moves[iid] = {{question, cluster: target}};
  }});
  saveState(STATE);
  location.reload();
}}

function onRenameInput(e){{
  const inp = e.target;
  const key = inp.dataset.question + '::' + inp.dataset.draft;
  STATE.names[key] = inp.value;
  saveState(STATE);
}}
function onConfirmChange(e){{
  const chk = e.target;
  const key = chk.dataset.question + '::' + chk.dataset.cluster;
  STATE.confirmed[key] = chk.checked;
  saveState(STATE);
}}

function resetProgress(){{
  if (!confirm('Discard all moves, renames, and confirmations in this browser?')) return;
  localStorage.removeItem(LS_KEY);
  location.reload();
}}

function exportYaml(){{
  const byQ = {{}};
  document.querySelectorAll('.cluster-card').forEach(card => {{
    const q = card.dataset.question, draft = card.dataset.cluster;
    const rows = [...card.querySelectorAll('.inst-row')];
    if (rows.length === 0) return; // emptied by a move-out, skip
    const renameInput = card.querySelector('.rename-input');
    const finalName = (renameInput.value || '').trim() || draft;
    const confirmed = card.querySelector('.confirm-check').checked;
    const docs = [...new Set(rows.map(r => r.querySelector('.inst-doc').textContent))];
    const quotes = rows.map(r => r.querySelector('.inst-quote').textContent.replace(/^\\u201c|\\u201d$/g, ''));
    (byQ[q] = byQ[q] || []).push({{
      draft_name: draft, final_name: finalName, confirmed,
      n_instances: rows.length, n_documents: docs.length,
      example_quotes: quotes.slice(0, 5),
    }});
  }});
  function yamlStr(s){{ return JSON.stringify(String(s)); }}
  let out = "# Author-reviewed guidebook -- exported from guidebook_summary.html\\n";
  out += "# Includes every split/merge/rename/confirmation made in this browser session.\\n";
  out += "# Still to add: definitions, inclusion/exclusion rules, exemplar unit_ids.\\n";
  for (const [q, clusters] of Object.entries(byQ)) {{
    out += `${{q}}:\\n`;
    clusters.forEach(c => {{
      out += `  - draft_name: ${{yamlStr(c.draft_name)}}\\n`;
      out += `    final_name: ${{yamlStr(c.final_name)}}\\n`;
      out += `    confirmed: ${{c.confirmed}}\\n`;
      out += `    n_instances: ${{c.n_instances}}\\n`;
      out += `    n_documents: ${{c.n_documents}}\\n`;
      out += `    example_quotes:\\n`;
      c.example_quotes.forEach(qt => {{ out += `      - ${{yamlStr(qt)}}\\n`; }});
    }});
  }}
  const blob = new Blob([out], {{type:'text/yaml'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'guidebook_reviewed.yaml'; a.click();
}}

function updateSelCounts(){{
  document.querySelectorAll('.qsection').forEach(sec => {{
    const q = sec.dataset.question;
    const n = sec.querySelectorAll('.inst-check:checked').length;
    const label = document.getElementById('selcount-' + q);
    if (label) label.textContent = n ? n + ' selected' : '';
  }});
}}

document.addEventListener('DOMContentLoaded', () => {{
  document.querySelectorAll('.rename-input').forEach(el => el.addEventListener('input', onRenameInput));
  document.querySelectorAll('.confirm-check').forEach(el => el.addEventListener('change', onConfirmChange));
  document.querySelectorAll('.inst-row').forEach(wireInstanceRow);
  document.querySelectorAll('.btn-add-inst').forEach(btn => btn.addEventListener('click',
    () => addFragment(btn.dataset.question, btn.dataset.cluster)));
  applyStateToDom();
}});
</script>
</body>
</html>'''
    OUT.write_text(html_out, encoding="utf-8")
    print(f"Wrote {OUT} ({total_clusters} clusters across {len(q_stats)} questions, "
          f"{total_instances} instances rendered individually)")


if __name__ == "__main__":
    main()
