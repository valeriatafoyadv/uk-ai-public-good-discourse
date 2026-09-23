# AI for the public good: Corpus and analysis pipeline.
### Discourse analysis · GDS/DSIT, United Kingdom · documents published 18 January 2024 – 2 July 2026

Pipeline part of the dissertation submitted in part-fulfilment of the MPA in Innovation, Public Policy and Public Value 
(UCL Institute for Innovation and Public Purpose, 2026) on
Discourse and construction of imaginaries of "AI for the public good" in the United Kingdom's Government Digital Service (GDS) and Department for Science, Innovation and Technology (DSIT)'s Machinery of Government Changes, 2024–2026.

**Guiding principles summarized: the language model locates and extracts; the author interprets and
consolidates.** The final interpretation and validation of the results rests with the author, who systematically reviews and approves each code and its corresponding data-based evidence.

## The corpus

**Data window.** 66 documents, published between 18 January 2024 and 2 July 2026 (the eligibility
window runs to 31 July 2026, so the 21 July 2026 machinery-of-government change falls inside it).
The texts in `data/text/` were retrieved between 29 August and 10 September 2026; each file records
its own retrieval time in `fetched_at`.

The documents are listed in
[`data/manifest.csv`](data/manifest.csv) with genre, date, authorship side, partnership
family, and whether the phrase or a named variant occurs.

| Genre | Documents |
|---|---|
| Strategy papers | 9 |
| Memoranda of understanding (MoU) | 9 |
| Company press releases | 12 |
| Government press releases | 7 |
| Blog posts | 21 |
| Written ministerial statements | 7 |
| Regulatory response | 1 |

24 of the 66 sit in one of eight partnership families (Anthropic, Cohere, OpenAI, Google
DeepMind, ElevenLabs, NVIDIA, Cisco, Synthesia); the other 42 are government-authored.
[`docs/corpus.md`](docs/corpus.md) lists all 66 with a link to the source and, where one was
captured, a web archive snapshot.

`data/text/` holds the structured text (title, heading, body, quotation blocks) of the 54
GOV.UK and parliament.uk documents, reproduced under the [Open Government Licence
v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) — Contains
public sector information licensed under the Open Government Licence v3.0. It does not hold the
text of the 12 company press releases, which are not covered by that licence; `docs/corpus.md`
links to those instead, and `02b_fetch_companies.py` re-fetches them from their source URL.

## What the pipeline does

The dissertation codes the corpus in four rounds. Rounds 1.1, 2.1, and 2.2 are the author's own
interpretive coding in NVivo; the pipeline supplies Round 1.2 and the computed layers that the
author reads against the manual coding in Rounds 2.1 and 2.2. The NVivo project itself is not in
this repository. Two exports from it supported that manual coding: a **codebook export**, NVivo's
standard listing of the project's codes with their descriptions and how many sources and
references each has, and a **coded-passage report** written for this project, which instead lists
each coded instance with the surrounding text, the code's position in the passage, and its parent
and child codes in the author's hierarchy — richer than the codebook because it carries enough
detail to compute how often a code repeats and what share of a document's words fall under it, not
just which codes exist.

| Round | What the pipeline does | Scripts | Output |
|---|---|---|---|
| 1.2 | Splits each document into coding units, runs the seven core questions plus AGENCY, MODALITY, METAPHOR, and DEFINITIONAL over every unit with a language model, and checks that every extracted quotation is verbatim | `04_segment.py`, `05_code.py` | `coding/units.jsonl`, `coding/round1/*.jsonl` |
| 1.2 | Groups the coded answers by embedding similarity into candidate sub-codes for the author to name | `06_consolidate.py` | `coding/guidebook_draft.yaml` (and a metaphor report, `analysis/metaphors_report.md`, written when the step runs) |
| 2.1 | Builds the citation network: explicit references, echoed phrasing, and the one declared supersession | `06_network_v0.py` | `analysis/networks/intertextual_v0.json`, `analysis/networks/authorship_family_map.html` |
| 2.2 | Detects phrases shared between government and company documents in each partnership family, and tabulates AGENCY by genre | `07_echo.py`, `11_agency_query.py`, `07b_queries.py` | `analysis/queries/` |

Corpus preparation: `01_manifest.py` builds the manifest, `02a_fetch_gov.py` and
`02b_fetch_companies.py` fetch and structure the documents, and `03_qa_merge.py` checks the
extraction. `add_document.py` applies the admission checklist to a new document (e.g. publication
window, voice, remit, institutional blogs, no scrutiny or spoken-word documents) and asks for the
author's confirmation before anything enters the corpus.
`10_finalize.py` re-runs the analysis chain from the data on disk.

### Language models used

Three engines produced the 2,711 coding records that returned an extract, and every record stores
its model, prompt version, and run identifier.

| Engine | Records | Notes |
|---|---|---|
| `kimi-k3:cloud` | 1,175 (43%) | Chosen in a model evaluation on verbatim fidelity (97.6%; `coding/model_eval/decision.md`) |
| `deepseek-v4-flash:cloud` | 1,217 (45%) | Took over most remaining calls when usage limits made further `kimi-k3` use impractical |
| Claude Code agent (`claude-code-local`) | 319 (12%) | Coded documents added after the automated run, under the same rule |

Using three engines was an operational substitution under a rate limit, not a designed comparison,
and the method says so; `kimi-k3:cloud` stayed the model of record throughout. What keeps it
defensible is that every record carries its engine and passes the same per-quotation
`quote_verified` check, so the fidelity gap between engines is auditable record by record, not
just asserted from the aggregate.

The choice of `kimi-k3:cloud` itself came from an evaluation, not a default: four candidate models
were run on the same six units against all eleven questions (66 calls each) and scored on valid
JSON output, verbatim quotation fidelity, and a reasonable `applies=false` rate on short passages.
Full results and the decision rule are in [`coding/model_eval/decision.md`](coding/model_eval/decision.md)
and [`results.csv`](coding/model_eval/results.csv).

2,682 of the 2,711 quotations were verbatim; the 29 that were not are flagged (`quote_verified = false`).
Embeddings for clustering use `embeddinggemma`, run locally through Ollama.

## Documentation

| Page | What it covers |
|---|---|
| [`docs/corpus.md`](docs/corpus.md) | The 66 documents with a link to each source and, where captured, an archive snapshot |
| [`docs/memos.md`](docs/memos.md) | Six of the author's Round 1.1 analytical memos, lightly edited |
| [`docs/figures.md`](docs/figures.md) | The dissertation's figures, the interactive citation network, and the query and echo-phrase appendix |
| [`docs/pipeline.md`](docs/pipeline.md) | Each step in run order: inputs, what it does, outputs, and where the dissertation reports it |
| [`docs/crosswalk.md`](docs/crosswalk.md) | Every table, figure, and reported number of the dissertation, against the file and script that produce it |
| [`docs/prompts.md`](docs/prompts.md) | The coding prompts the model received, reproduced for replication (pipeline instructions only) |
| [`docs/data_dictionary.md`](docs/data_dictionary.md) | Every data file and its fields, types, and codes, with the data window |

## Data dictionary

The full data dictionary is in [`docs/data_dictionary.md`](docs/data_dictionary.md). The main files:

| File | One row or record per | Count | Key fields |
|---|---|---|---|
| `data/manifest.csv` | Document | 66 | `doc_id`, `date`, `genre`, `side`, `family`, `term_status`, `url` |
| `data/text/<doc_id>.json` | Document (GOV.UK and parliament.uk) | 54 | `source_url`, `fetched_at`, `blocks` (with `structural_position`) |
| `coding/units.jsonl` | Coding unit | 91 | `unit_id`, `text`, `retrieval` |
| `coding/round1/<doc_id>.jsonl` | Unit, question, and instance | 2,711 with an extract | `question`, `answer_summary`, `verbatim_quote`, `quote_verified`, `model`, `run_id` |
| `coding/guidebook_draft.yaml` | Candidate sub-code cluster | — | `candidate_name`, `n_instances`, `example_quotes` |
| `analysis/networks/intertextual_v0.json` | Document and link | 66 nodes, 115 edges | `type` (`reference`, `echo`, `supersession`), `evidence` |
| `analysis/queries/*.csv` | Varies | — | Term counts, echo phrases, AGENCY by genre |

Genre codes: `STRAT` strategy paper, `MOU` memorandum of understanding, `PRCO` company press release,
`PRGOV` government press release, `BLOG` blog post, `WMS` written ministerial statement, `REG`
regulatory response.

## Reproducing it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
ollama pull embeddinggemma        # only for segmentation retrieval and clustering
.venv/bin/python scripts/10_finalize.py
```

The coding records, structured texts, and network are in the repository, so the tables and figures of
Chapter 5 can be regenerated from them without calling a language model again (steps 6 to 9 of
[`docs/pipeline.md`](docs/pipeline.md)), except that steps reading `data/text/` will fail on the 12
company documents until `02b_fetch_companies.py` re-fetches them locally — see above. Requirements: Python 3.13 or later and, for segmentation
retrieval and clustering, [Ollama](https://ollama.com) on `localhost:11434`. Re-running the coding step
(`05_code.py`) needs access to the language models named above. On Windows, use `.venv\Scripts\python.exe`.

`10_finalize.py` copies `coding/guidebook_draft.yaml` to a dated backup before it runs. The BENEFICIARY and
MECHANISM sub-codes in that file were recoded by hand, and the consolidation step overwrites the
file with an automated draft.

## Repository layout

```
data/manifest.csv        the 66 documents and their attributes
data/text/               structured text of the 54 GOV.UK/parliament.uk documents (OGL)
coding/prompts/          prompts for the eleven questions and the document profile, versioned
coding/round1/           raw coding records (JSONL per document, with model and run metadata)
coding/model_eval/       the model comparison and the decision
coding/guidebook_draft.yaml  candidate sub-codes; BENEFICIARY and MECHANISM recoded by hand
analysis/networks/       citation network (JSON with evidence) and interactive map
analysis/queries/        term counts, echo phrases, AGENCY by genre
analysis/nvivo/          the coded passages and the document classification, as sheets for NVivo
analysis/guidebook_summary.html  review page for the candidate sub-codes
data/raw/                source URL, hash, and retrieval record per document
data/embeddings/         stored embeddings used for retrieval and clustering
docs/                    pipeline steps, crosswalk to the dissertation, data dictionary
scripts/                 the pipeline scripts, numbered in the order they run
```

## Licence

The code and the author's own data (coding records, codebook, network, queries, and documentation)
are released under the [MIT Licence](LICENSE). The document texts in `data/text/` are Crown copyright
and are reproduced under the [Open Government Licence
v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/), not the MIT
Licence. The company press releases are not reproduced here and remain under their publishers'
terms.

## How to cite

Tafoya, V. (2026). *AI for the public good: Corpus and analysis pipeline* [Computer software].
https://github.com/valeriatafoyadv/uk-ai-public-good-discourse
