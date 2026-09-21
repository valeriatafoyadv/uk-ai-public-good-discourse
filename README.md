# AI for the public good — corpus and analysis pipeline
### Discourse analysis · GDS/DSIT, United Kingdom · January 2024 – July 2026

Pipeline behind an MPA dissertation (UCL Institute for Innovation and Public Purpose, 2026) on
"AI for the public good" as a sociotechnical imaginary in UK government discourse on AI in
public services, anchored on the Government Digital Service (GDS).

**Guiding principle: the language model locates and extracts; the author interprets and
consolidates.** No interpretive result is final until the author has checked it.

## The corpus

66 documents, published between 18 January 2024 and 2 July 2026, listed in
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
The full text of each document is in `data/text/`, structured as title, heading, body, and
quotation blocks.

## What the pipeline does

The dissertation codes the corpus in four rounds. Rounds 1.1, 2.1, and 2.2 are the author's own
interpretive coding in NVivo; the pipeline supplies Round 1.2 and the computed layers that the
author reads against the manual coding in Rounds 2.1 and 2.2.

| Round | What the pipeline does | Scripts | Output |
|---|---|---|---|
| 1.2 | Splits each document into coding units, runs the seven core questions plus AGENCY, MODALITY, METAPHOR, and DEFINITIONAL over every unit with a language model, and checks that every extracted quotation is verbatim | `04_segment.py`, `05_code.py` | `coding/units.jsonl`, `coding/round1/*.jsonl` |
| 1.2 | Groups the coded answers by embedding similarity into candidate sub-codes for the author to name | `06_consolidate.py` | `coding/guidebook_draft.yaml` (and a metaphor report, `analysis/metaphors_report.md`, written when the step runs) |
| 2.1 | Builds the citation network: explicit references, echoed phrasing, and the one declared supersession | `06_network_v0.py` | `analysis/networks/intertextual_v0.json`, `analysis/networks/authorship_family_map.html` |
| 2.2 | Detects phrases shared between government and company documents in each partnership family, and tabulates AGENCY by genre | `07_echo.py`, `11_agency_query.py`, `07b_queries.py` | `analysis/queries/` |

Corpus preparation: `01_manifest.py` builds the manifest, `02a_fetch_gov.py` and
`02b_fetch_companies.py` fetch and structure the documents, and `03_qa_merge.py` checks the
extraction. `add_document.py` applies the admission checklist to a new document (publication
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

2,682 of the 2,711 quotations were verbatim; the 29 that were not are flagged (`quote_verified = false`).
Embeddings for clustering use `embeddinggemma`, run locally through Ollama.

## Documentation

| Page | What it covers |
|---|---|
| [`docs/pipeline.md`](docs/pipeline.md) | Each step in run order: inputs, what it does, outputs, and where the dissertation reports it |
| [`docs/crosswalk.md`](docs/crosswalk.md) | Every table, figure, and reported number of the dissertation, against the file and script that produce it |
| [`docs/prompts.md`](docs/prompts.md) | The coding prompts the model received, reproduced for replication (pipeline instructions only) |
| [`docs/data_dictionary.md`](docs/data_dictionary.md) | The fields of every data file |

## Reproducing it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
ollama pull embeddinggemma        # only for segmentation retrieval and clustering
.venv/bin/python scripts/10_finalize.py
```

The coding records, structured texts, and network are in the repository, so the tables and figures of
Chapter 5 can be regenerated from them without calling a language model again (steps 6 to 9 of
[`docs/pipeline.md`](docs/pipeline.md)). Requirements: Python 3.13 or later and, for segmentation
retrieval and clustering, [Ollama](https://ollama.com) on `localhost:11434`. Re-running the coding step
(`05_code.py`) needs access to the language models named above. On Windows, use `.venv\Scripts\python.exe`.

`10_finalize.py` copies `coding/guidebook_draft.yaml` to a dated backup before it runs. The BENEFICIARY and
MECHANISM sub-codes in that file were recoded by hand, and the consolidation step overwrites the
file with an automated draft.

## Repository layout

```
data/manifest.csv        the 66 documents and their attributes
data/text/               structured text of every document
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
