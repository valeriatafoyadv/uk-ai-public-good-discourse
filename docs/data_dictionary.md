# Data dictionary

This page lists the fields of every data file in the repository. For how each file is produced, see
[`pipeline.md`](pipeline.md). For which table or figure uses it, see [`crosswalk.md`](crosswalk.md).

**Data window.** The corpus covers documents published from 18 January 2024 to 2 July 2026 (the
eligibility window runs to 31 July 2026). The texts in `data/text/` were retrieved between
29 August and 10 September 2026, and each file records its own retrieval time in `fetched_at`.

## Files at a glance

| File | One row or record per | Count |
|---|---|---|
| [`data/manifest.csv`](#datamanifestcsv) | Document | 66 |
| [`data/text/<doc_id>.json`](#datatextdoc_idjson) | Document (GOV.UK and parliament.uk only) | 54 |
| [`data/raw/<doc_id>.meta.json`](#datarawdoc_idmetajson) | Retrieval record (first intake) | 36 |
| [`data/embeddings/`](#dataembeddings) | Embedded section or search probe | 538 sections, 3 probes |
| [`coding/lexicon_v1.yaml`](#codinglexicon_v1yaml) | Search pattern | — |
| [`coding/units.jsonl`](#codingunitsjsonl) | Coding unit | 91 |
| [`coding/round1/<doc_id>.jsonl`](#codinground1doc_idjsonl) | Unit, question, and instance | 2,711 records with an extract |
| [`coding/round1/doc_profiles.jsonl`](#codinground1doc_profilesjsonl) | Document | 66 |
| [`coding/guidebook_draft.yaml`](#codingguidebook_draftyaml) | Candidate sub-code cluster | — |
| [`coding/model_eval/results.csv`](#codingmodel_evalresultscsv) | Model, unit, and question | 264 |
| [`analysis/networks/intertextual_v0.json`](#analysisnetworksintertextual_v0json) | Document (node) and link (edge) | 66 nodes, 115 edges |
| [`analysis/queries/`](#analysisqueries) | Varies by file | — |
| [`analysis/nvivo/`](#analysisnvivo) | Coded passage, or document | 2,706 and 66 |

## `data/manifest.csv`

One row per document.

| Field | Type | Meaning |
|---|---|---|
| `doc_id` | text | Identifier in the form `date_GENRE_Publisher_ShortTitle`. The key used in every other file |
| `excel_row` | integer | Row in the selection spreadsheet |
| `date` | date | Publication date (YYYY-MM-DD) |
| `genre` | code | See [Genre codes](#genre-codes) |
| `actor_raw` | text | The publisher as recorded in the selection spreadsheet |
| `speaker` | text | Body whose voice the text is in, for example `DSIT`, `GDS`, `OpenAI`, or a joint form such as `DSIT_and_NVIDIA` |
| `side` | code | `Public`, `Private`, `Private (partnership)`, or `Public, led by external actor` |
| `family` | code | Partnership family (`Anthropic`, `Cohere`, `OpenAI`, `DeepMind`, `ElevenLabs`, `NVIDIA`, `Cisco`, `Synthesia`) or `None` |
| `gds_tier` | code | Provisional tier: `T1` GDS or CDDO authorship, `T2` GDS named in the text, `T3` absent |
| `gds_tier_source` | text | How `gds_tier` was set. Every value is automatic and provisional |
| `stage` | text | Working label from the selection spreadsheet, not used in the analysis |
| `term_status` | code | `present` (the phrase), `variant` (a close variant such as "public benefit"), or `absent`. Set by `04_segment.py` from the lexicon |
| `url` | URL | Source address |
| `archive_url` | URL | Web archive snapshot, where one exists |
| `corpus_version` | integer | Version in which the document entered the corpus: `1` for the 35 documents of the first intake, then one version per added document |
| `is_context` | boolean | Legacy flag from the first intake; `false` for all 66 documents |
| `fetch_status` | code | Result of retrieval (`ok` for all 66) |
| `source` | code | How the text was retrieved: `direct` (64) or `browser_prefetch` (2) |
| `n_blocks`, `n_quotes`, `n_pillars` | integer | Number of text blocks, quotation blocks, and pillar headings extracted |
| `total_chars` | integer | Length of the extracted text in characters |

### Genre codes

| Code | Genre | Documents |
|---|---|---|
| `STRAT` | Strategy paper | 9 |
| `MOU` | Memorandum of understanding | 9 |
| `PRCO` | Company press release | 12 |
| `PRGOV` | Government press release | 7 |
| `BLOG` | Blog post | 21 |
| `WMS` | Written ministerial statement | 7 |
| `REG` | Regulatory response | 1 |

## `data/text/<doc_id>.json`

Structured text of each GOV.UK and parliament.uk document, under the Open Government Licence v3.0.
The 12 company press releases are not included (see the README).

| Field | Type | Meaning |
|---|---|---|
| `doc_id` | text | Document identifier |
| `source_url` | URL | Address the text was retrieved from |
| `fetched_at` | timestamp | Retrieval time (ISO 8601, with time zone) |
| `format` | code | Source format: `html` (50) or `pdf` (4) |
| `blocks` | list | The text, in reading order. Each block has the four fields below |
| `blocks[].block_id` | text | Block identifier within the document |
| `blocks[].structural_position` | code | `title`, `pillar_name`, `section_heading`, `body`, or `quotation` |
| `blocks[].heading_path` | list | The headings the block sits under |
| `blocks[].text` | text | The block's text |

## `data/raw/<doc_id>.meta.json`

Retrieval record, kept for the documents of the first intake.

| Field | Type | Meaning |
|---|---|---|
| `doc_id` | text | Document identifier |
| `fetch_status` | code | Result of retrieval |
| `http_status` | integer | HTTP status code returned |
| `content_type` | text | MIME type returned |
| `final_url` | URL | Address after redirects |
| `sha256` | text | Hash of the retrieved file, to check that a source has not changed |
| `bytes` | integer | Size of the retrieved file |
| `n_blocks` | integer | Blocks extracted |
| `error` | text | Error message, if retrieval failed |

## `data/embeddings/`

| File | Contents |
|---|---|
| `sections_embeddinggemma.npz` | Embedding of each of the 538 document sections, used to retrieve coding units |
| `sections_index.json` | Which document and section each row of the sections file belongs to |
| `probes_embeddinggemma.npz` | Embeddings of the three search probes used for semantic retrieval |
| `meta.json` | `model` (`embeddinggemma`), `dim` (768), `n_sections`, `normalisation` (L2), `truncation_chars` (1,500), `lexicon_version`, and the text of the `probes` |

## `coding/lexicon_v1.yaml`

The search patterns that find the phrase and its variants.

| Key | Meaning |
|---|---|
| `version` | Lexicon version. Changes create a new version rather than editing this one |
| `nominal` | Patterns for the phrase itself; a match sets `term_status` to `present` |
| `variant_nominal` | Patterns for close variants; a match sets `term_status` to `variant` |
| `distributive` | Related forms that are counted but do not set `term_status` |
| `beneficiary_probes` | Sentences used as probes for semantic retrieval |

## `coding/units.jsonl`

One coding unit per line: the passage a model is asked to code.

| Field | Type | Meaning |
|---|---|---|
| `unit_id` | text | `doc_id::sNN` for a section, or `doc_id::full` for a document coded whole |
| `heading` | text | Section heading |
| `block_ids` | list | Blocks that make up the unit |
| `text` | text | The unit's text |
| `retrieval` | code | How the unit was found: `lexicon` (53), `full_short_doc` (33), `semantic` (3), or `manual_full_over_threshold` (2, a long document coded whole) |
| `hits_nominal`, `hits_variant`, `hits_distributive` | integer | Lexicon matches inside the unit |

## `coding/round1/<doc_id>.jsonl`

One record per unit, question, and instance.

| Field | Type | Meaning |
|---|---|---|
| `doc_id`, `unit_id`, `heading` | text | Where the record comes from |
| `question` | code | `BENEFICIARY`, `MECHANISM`, `SAFEGUARD`, `RESPONSIBILITY`, `PROJECTED_FUTURE`, `ACTANTS`, `NATURALISED_ORDER`, `DEFINITIONAL`, `AGENCY`, `MODALITY`, or `METAPHOR` |
| `so_tags` | list | The specific objectives (`SO1`, `SO2`, `SO3`) the question serves |
| `model` | text | Engine that produced the record |
| `prompt_version` | integer | Version of `coding/prompts/prompts_v1.yaml` used |
| `run_id` | text | Coding run identifier (see `run_meta.json`) |
| `timestamp` | timestamp | When the record was produced |
| `applies` | boolean | Whether the question applies to the passage |
| `confidence` | number | The model's stated confidence, 0 to 1 |
| `answer_summary` | text | One-line answer; this is what the clustering step embeds |
| `verbatim_quote` | text | The quotation the answer rests on |
| `quote_verified` | boolean | `true` if the quotation appears verbatim in the source text |
| `instance_data` | JSON | The full structured answer. Its fields depend on the question (see below) |
| `error` | text | Present only if the call failed; every analysis step skips these records |

### Controlled vocabularies inside `instance_data`

| Question | Field | Values (instances) |
|---|---|---|
| AGENCY | `form` | `explicit_agent` (264), `agentless_passive` (63), `nominalisation` (81) |
| MODALITY | `modality` | `deontic` (110), `epistemic` (268) |
| ACTANTS | `threat_type` | `technological_risk`, `geopolitical_lag`, `bureaucratic_status_quo`, `public_distrust`, `other`, `n/a` |
| METAPHOR | `lj_type` | `structural`, `orientational`, `ontological`, `personification` (Lakoff & Johnson, 1980) |

### Other files in `coding/round1/`

| File | Contents |
|---|---|
| `doc_profiles.jsonl` | One document-level profile per document (fields below) |
| `definitional_instances.jsonl` | The DEFINITIONAL records that apply, in date order |
| `run_meta.json` | Log of the five coding runs (`runs`). Each run records `run_id`, `timestamp`, `model`, `prompt_version`, the documents and questions covered, counts of units, calls, and records, the success rate, the share of verified quotations, and `status` |

## `coding/round1/doc_profiles.jsonl`

| Field | Type | Meaning |
|---|---|---|
| `doc_id`, `model`, `prompt_version`, `run_id`, `timestamp`, `error` | — | As in the coding records |
| `function` | text | What the document is for |
| `audience` | code | `parliament`, `practitioners`, `general_public`, `industry`, or `mixed` |
| `force` | text | Recommendation, commitment, or obligation, and how compliance is secured |
| `narrative_arc` | code | `beginning`, `middle`, or `end` (Kaplan, 1993) |
| `arc_rationale` | text | One-sentence reason for the arc assigned |

## `coding/guidebook_draft.yaml`

The candidate codebook.

| Field | Meaning |
|---|---|
| `status`, `generated_from`, `embedding_model`, `note` | How and from what the draft was produced |
| `similarity_threshold` | Cosine similarity at which answers are grouped (0.75) |
| `questions.<QUESTION>.n_applies_true` | Records for the question where `applies` is true |
| `questions.<QUESTION>.n_clusters` | Number of candidate clusters |
| `questions.<QUESTION>.recoding_note` | Present for BENEFICIARY and MECHANISM, which were recoded by hand |
| `clusters[].candidate_name` | Working name of the cluster |
| `clusters[].n_instances` | Records in the cluster |
| `clusters[].example_quotes` | Sample quotations |
| `clusters[].member_unit_ids` | Units the cluster draws on |
| `clusters[].status` | Review status |

## `coding/model_eval/results.csv`

One row per model, unit, and question in the model evaluation (four models, six units, eleven
questions). The decision is in [`decision.md`](../coding/model_eval/decision.md).

| Field | Type | Meaning |
|---|---|---|
| `model` | text | Model tested |
| `unit_id`, `question` | text | What was coded |
| `passage_len` | integer | Length of the passage in characters |
| `elapsed_s` | number | Response time in seconds |
| `json_valid` | boolean | Whether the output was valid JSON |
| `applies` | boolean | The model's `applies` answer |
| `n_quotes`, `n_quotes_verbatim_ok` | integer | Quotations returned, and how many were verbatim |
| `error` | text | Error, if the call failed |
| `raw_response` | text | The model's full output |

## `analysis/networks/intertextual_v0.json`

| Element | Field | Meaning |
|---|---|---|
| `nodes` (66) | `id`, `label`, `date`, `genre`, `speaker`, `family`, `term_status` | The document and its attributes |
| | `in_degree` | How many documents link to it |
| `edges` (115) | `source`, `target` | Linking and linked document |
| | `type` | `reference` (99), `echo` (15), or `supersession` (1) |
| | `count` | Number of times the link occurs |
| | `evidence` | The text that supports the link, so each edge can be checked |

## `analysis/queries/`

| File | Fields |
|---|---|
| `echo_phrases.csv` | `family`, `gov_doc`, `company_doc`, `n_words`, `phrase`, `published_first`, `formulaic` |
| `term_counts.csv` | `doc_id`, `genre`, `speaker`, `family`, `n_nominal`, `n_variant`, `n_distributive`, `nominal_forms` |
| `agency_by_genre.csv` | `genre`, `explicit_agent`, `agentless_passive`, `nominalisation` |
| `zero_count_by_genre.csv` | `genre`, `docs_present`, `docs_variant`, `docs_absent`, `total_nominal_mentions`, `total_variant_mentions` |
| `nominal_by_gdstier.csv` | `gds_tier`, then the same fields as `zero_count_by_genre.csv` |
| `queries.html`, `echo_summary.html`, `echo_summary.md` | Charts and summaries drawn from the files above |

## `analysis/nvivo/`

Sheets for importing the computed coding into NVivo.

| File | Fields |
|---|---|
| `coded_passages.csv` | `doc_id`, `unit_id`, `question`, `sub_answer`, `verbatim_quote`, `quote_verified`, `model`, `run_id` |
| `classification_sheet.csv` | `doc_id`, `Genre`, `Speaker`, `Side`, `Family`, `GDSTier`, `Stage`, `TermStatus`, `Year` |
