# The analysis pipeline, step by step

This page describes each step of the analysis: what it takes in, what it does, what it writes, and
where the dissertation reports it. Steps run in the order below. [`crosswalk.md`](crosswalk.md)
lists every table, figure, and number of the dissertation against the file that produces it, and
[`data_dictionary.md`](data_dictionary.md) describes the fields of each file.

**Principle.** The language model locates and extracts; the author interprets and consolidates. The
author's own coding (Rounds 1.1, 2.1, and 2.2) was done in NVivo and is not in this repository. The
pipeline supplies Round 1.2 and the computed layers that the author reads against the manual coding.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
ollama pull embeddinggemma        # only for segmentation retrieval and clustering
```

On Windows, use `.venv\Scripts\python.exe`. Python 3.13 or later. The coding step calls
language models through Ollama (local `embeddinggemma`; `kimi-k3:cloud` and
`deepseek-v4-flash:cloud` through Ollama Cloud). The counts the dissertation reports can be
recomputed from the files in the repository without calling a cloud model again (steps 6 to 9).

## Order of steps

| # | Step | Script | Reads | Writes | Reported in |
|---|---|---|---|---|---|
| 1 | Corpus manifest | `01_manifest.py [spreadsheet.xlsx]` | the selection spreadsheet (not in the repository) | `data/manifest.csv` | 3.4, Appendix A |
| 2 | Fetch and structure | `02a_fetch_gov.py`, `02b_fetch_companies.py` | manifest URLs | `data/text/*.json`, `data/raw/*.meta.json` | 3.4 |
| 3 | Extraction check | `03_qa_merge.py` | `data/text/`, `data/raw/*.meta.json` | updates the manifest (fetch status, block counts) | 3.4 |
| 4 | Coding units | `04_segment.py` | `data/text/`, `coding/lexicon_v1.yaml` | `coding/units.jsonl`, `analysis/queries/term_counts.csv`; sets `term_status` in the manifest | 3.5 |
| 5 | Round 1.2 coding | `05_code.py` | `coding/units.jsonl`, `coding/prompts/prompts_v1.yaml` | `coding/round1/*.jsonl` | 3.6, Table 2 |
| 6 | Candidate codebook | `06_consolidate.py` | `coding/round1/` | `coding/guidebook_draft.yaml`, `analysis/metaphors_report.md` (written when the step runs) | 5.3 to 5.5, Appendix H |
| 7 | Echo phrases | `07_echo.py` | `data/text/`, manifest | `analysis/queries/echo_phrases.csv`, `echo_summary.md` | 5.6.1, 5.6.2 |
| 8 | Citation network | `06_network_v0.py` | `data/text/`, manifest, `echo_phrases.csv` | `analysis/networks/intertextual_v0.json` | 5.6.1, Figure 3 |
| 9 | AGENCY by genre, count queries | `11_agency_query.py`, then `07b_queries.py` | `coding/round1/`, manifest, `term_counts.csv` | `analysis/queries/agency_by_genre.csv`, `zero_count_by_genre.csv`, `nominal_by_gdstier.csv`, `queries.html` | 5.6.2, Table 9 |
| | Add a document | `add_document.py <url>` | a URL | manifest row, `data/text/`, coding units | 3.4 |

The model evaluation (`coding/model_eval/`) ran once, before step 5, and is not part of the run order.

## What each step does

### 1. Corpus manifest
Builds one row per document: date, genre (STRAT, MOU, PRGOV, PRCO, BLOG, WMS, REG), speaker,
authorship side, partnership family, term status, source URL, and corpus version. The repository
holds the result (66 documents), so this step does not need to be re-run.

### 2. Fetch and structure
Downloads each document (government documents from GOV.UK and parliament.uk, company documents from
company newsrooms and blogs), falls back to a web archive snapshot if the page fails, and extracts
the text as ordered blocks labelled title, pillar name, section heading, body, or quotation. Original
PDF and HTML files are not kept in the repository; each document's source URL, hash, and retrieval
record are in `data/raw/<doc_id>.meta.json`.

This public repository keeps the extracted text (`data/text/<doc_id>.json`) only for the 54 GOV.UK and
parliament.uk documents, under the Open Government Licence v3.0. It does not keep the text of the 12
company press releases (`docs/corpus.md` marks which); steps 4, 5, 7, and 8 below read every file in
`data/text/` and fail or under-count if a document is missing, not skip it silently — run
`02b_fetch_companies.py` first to regenerate those 12 files from their source URL.

### 3. Extraction check
For every document: valid JSON, non-empty, exactly one title block, block labels in the allowed
vocabulary, and a plausible length for its genre. Retrieval metadata is merged into the manifest.

### 4. Coding units
A unit is a section: the blocks under one top-level heading. Every document is scanned in full. For
documents that contain the phrase or a variant, the sections around it become units. For documents
where it is absent, units are retrieved by the lexicon of the distributive claim (phrases such as "working
people", "taxpayer", or "benefit all") and by embedding similarity to probe sentences (`embeddinggemma`), and each unit records
which retrieval found it. Short documents are coded whole. The result is 91 units: 53 found by the lexicon, 33 short documents coded whole, 3 by semantic retrieval, and 2 long documents coded whole by hand. The step also
records term status for every document (present 16, variant 7, absent 43) and a provisional GDS tier.

### 5. Round 1.2 coding
For every unit, the model answers eleven questions from `prompts_v1.yaml` (reproduced in [`prompts.md`](prompts.md)): the seven core questions
(BENEFICIARY, MECHANISM, SAFEGUARD, RESPONSIBILITY, PROJECTED_FUTURE, ACTANTS, NATURALISED_ORDER) and
DEFINITIONAL, AGENCY, MODALITY, and METAPHOR. A document-level profile is also produced for every
document. Each answer is a structured record with a verbatim quotation. **Every quotation is checked
against the source text** and stored with `quote_verified`. Records that carry no quotation because the
question did not apply are kept (`applies = false`).

The model was chosen on a six-unit evaluation (`coding/model_eval/decision.md`): `kimi-k3:cloud` won on
verbatim fidelity (97.6%, with 100% valid output). Coding then ran on three engines, and each record stores its
engine, prompt version, and run identifier:

| Engine | Records that returned an extract |
|---|---|
| `kimi-k3:cloud` | 1,175 (43%) |
| `deepseek-v4-flash:cloud` | 1,217 (45%) |
| Claude Code agent (`claude-code-local`) | 319 (12%) |

In total, 3,052 records were written; 2,711 returned an extract, and 2,682 of those quotations are
verbatim (the other 29 are flagged). Options: `--doc <doc_id>`, `--questions core`, `--model <name>`.
The step also writes a 10-unit stratified sample for double coding (`coding/validation/sample_for_author.csv`, not kept in this repository).

### 6. Candidate codebook
For each core question, the short answers of every instance are embedded and grouped by cosine
similarity (threshold 0.75, single linkage). The output is a draft for the author to name, merge, or
reject. BENEFICIARY and MECHANISM were then recoded by hand: BENEFICIARY into ten categories where one
instance can carry several (321 labels over 284 instances), MECHANISM into 123 clusters, of which 13
hold more than one instance.

> **Warning.** This step overwrites `coding/guidebook_draft.yaml`, including the hand recoding. Copy
> the file aside before running it.

Automated clustering behaves unevenly: NATURALISED_ORDER barely merges (137 clusters for 182 instances),
while SAFEGUARD (167 of 182) and ACTANTS (171 of 204) collapse into one large cluster. This is
reported in 5.4 and 5.5. The step also writes a metaphor report (`analysis/metaphors_report.md`) that
groups the extracted figurative expressions; the dissertation notes it as a resource and does not analyse it.

### 7. Echo phrases
Finds sequences of six or more words that appear in both a government document and a company document
within the same partnership family, keeping only the longest sequence in each overlap. A phrase is marked
formulaic when it echoes in two or more families (generic language rather than one partnership's). Result:
51 shared phrases in 15 document pairs across seven families, none formulaic. Step 8 reads this file.

### 8. Citation network
Explicit references are found by matching curated, lowercase title aliases, masking long aliases
before short ones so nothing counts twice. For each partnership family, an announcement that names the
company and mentions the memorandum of understanding links to that family's memorandum. One
supersession is declared by hand (the AI Playbook supersedes the Generative AI Framework). Echo links
come from the shared phrases found in step 7 (one link per document pair). Result: 66 nodes and 115 links (99 reference, 15 echo, 1 supersession).
Each edge stores its evidence text, so every link can be audited. The author's NVivo coding is
compared with the network in 5.6.1.

`analysis/networks/authorship_family_map.html` is an interactive view of the same network. It embeds
the JSON; after re-running step 8, the embedded copy must be refreshed (`add_document.py` does this
itself).

### 9. AGENCY by genre and count queries
`11_agency_query.py` tabulates the AGENCY records (explicit agent, agentless passive, nominalisation)
by genre: 408 instances. `07b_queries.py` then adds the term-count queries (zero counts by genre,
nominal counts by GDS tier). MODALITY (378 instances: epistemic or deontic) is coded in the same records (`question = MODALITY`, `coding/round1/`) and can be tabulated from them directly.

### Adding a document
`add_document.py <url>` first applies the admission checklist to the document and, if it fails, stops
without writing anything (`--dry-run` shows the checklist only). A document is admitted only if it:

- was published between 18 January 2024 and 31 July 2026;
- is written, public, and official (GOV.UK or a company's own newsroom or blog);
- is in the voice of the actor under study, not a third party reporting on it;
- falls within the digital centre's remit (GDS, DSIT, the Incubator for AI, or digital government and AI in public services);
- if a blog, is an institutional and not a personal one;
- if a strategy, policy, or guidance document, claims that AI delivers benefit to the public.

Parliamentary scrutiny and audit reports and spoken-word transcripts are excluded. After the checklist
passes, the script asks for the author's confirmation, downloads and structures the document, adds the
manifest row with the next corpus version, creates its coding units, and refreshes the network.

## Records and traceability

- Every coding record stores model, prompt version, run identifier, timestamp, answer summary,
  confidence, verbatim quotation, and `quote_verified`.
- The manifest stores a corpus version for each document.
- Prompts are versioned in `coding/prompts/`.
- The author's manual coding is compared with each computed layer in the dissertation; where they
  converge, the convergence is reported.
