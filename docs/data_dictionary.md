# Data dictionary

The fields of every file the pipeline reads or writes. For where each file comes from, see
[`pipeline.md`](pipeline.md); for where the dissertation uses it, see [`crosswalk.md`](crosswalk.md).

## `data/manifest.csv`: one row per document (66)

| Field | Meaning |
|---|---|
| `doc_id` | Identifier: `date_GENRE_Publisher_ShortTitle`. Used as the key everywhere |
| `date` | Publication date |
| `genre` | STRAT strategy paper · MOU memorandum of understanding · PRGOV government press release · PRCO company press release · BLOG blog post · WMS written ministerial statement · REG regulatory response |
| `speaker` | Body whose voice the text is in (for example DSIT, GDS, OpenAI, or a joint form such as DSIT_and_NVIDIA) |
| `actor_raw` | The publisher as recorded in the selection spreadsheet |
| `side` | Public · Private · Private (partnership) · Public, led by external actor |
| `family` | Partnership family (Anthropic, Cohere, OpenAI, DeepMind, ElevenLabs, NVIDIA, Cisco, Synthesia) or `None` |
| `term_status` | `present` (the phrase), `variant` (a close variant such as public benefit), or `absent`, set by `04_segment.py` from the lexicon |
| `gds_tier` | Provisional tier: T1 GDS or CDDO authorship, T2 GDS named in the text, T3 absent. Every value is automatic and provisional (`gds_tier_source`) |
| `stage` | Working label from the selection spreadsheet, not used in the dissertation |
| `url`, `archive_url` | Source URL and, where one exists, the web archive snapshot |
| `corpus_version` | Version in which the document entered the corpus (1 for the 35 documents of the first intake, then one version number per added document) |
| `is_context` | Legacy flag from the first intake; false for all 66 documents |
| `fetch_status`, `source`, `n_blocks`, `n_quotes`, `n_pillars`, `total_chars` | Retrieval and extraction results, merged by `03_qa_merge.py` |
| `excel_row` | Row in the selection spreadsheet |

## `data/text/<doc_id>.json`: structured text

`doc_id`, `source_url`, `fetched_at`, `format`, and `blocks`: an ordered list of
`{block_id, structural_position, heading_path, text}`. `structural_position` is one of `title`,
`pillar_name`, `section_heading`, `body`, `quotation`.

## `data/raw/<doc_id>.meta.json`: retrieval record

`fetch_status`, `http_status`, `content_type`, `final_url`, `sha256`, `bytes`, `n_blocks`, `error`.

## `coding/units.jsonl`: coding units (91)

| Field | Meaning |
|---|---|
| `unit_id` | `doc_id::sNN` for a section, `doc_id::full` for a document coded whole |
| `heading`, `block_ids`, `text` | The section heading, its blocks, and its text |
| `retrieval` | How the unit was found: `lexicon` (53), `full_short_doc` (33), `semantic` (3), or `manual_full_over_threshold` (2, a long document coded whole) |
| `hits_nominal`, `hits_variant`, `hits_distributive` | Lexicon matches inside the unit |

## `coding/round1/<doc_id>.jsonl`: coding records

One record per unit, question, and instance.

| Field | Meaning |
|---|---|
| `doc_id`, `unit_id`, `heading` | Where the record comes from |
| `question` | BENEFICIARY, MECHANISM, SAFEGUARD, RESPONSIBILITY, PROJECTED_FUTURE, ACTANTS, NATURALISED_ORDER, DEFINITIONAL, AGENCY, MODALITY, or METAPHOR |
| `so_tags` | The specific objectives (SO1, SO2, SO3) the question serves |
| `model`, `prompt_version`, `run_id`, `timestamp` | Engine and run that produced the record |
| `applies` | Whether the question applies to the passage |
| `confidence` | The model's stated confidence, 0 to 1 |
| `answer_summary` | One-line answer (what the clustering step embeds) |
| `verbatim_quote` | The quotation the answer rests on |
| `quote_verified` | True if the quotation appears verbatim in the source text |
| `instance_data` | The full structured answer as JSON |

Other files in the folder: `doc_profiles.jsonl` (one document-level profile per document: function,
audience, force, narrative arc), `definitional_instances.jsonl` (the DEFINITIONAL records that apply,
in date order), and `run_meta.json` (the log of coding runs).

Vocabularies. AGENCY `form`: `explicit_agent` (264), `agentless_passive` (63), `nominalisation` (81).
MODALITY: `deontic` (110), `epistemic` (268). ACTANTS `threat_type`: `technological_risk`,
`geopolitical_lag`, `bureaucratic_status_quo`, `public_distrust`, `other`, `n/a`. METAPHOR `lj_type`
(Lakoff & Johnson 1980): `structural`, `orientational`, `ontological`, `personification`. DOC_PROFILE
`audience`: `parliament`, `practitioners`, `general_public`, `industry`, `mixed`. These enums were
originally specified in Spanish in the prompt; the prompt and every existing coding record were
normalised to English on 2026-09-22, verified against `verbatim_quote` to confirm no extracted text
changed (see `coding/prompts/prompts_v1.yaml`'s header comment).

## `coding/guidebook_draft.yaml`: candidate codebook

`status`, `generated_from`, `similarity_threshold` (0.75), `embedding_model`, and `questions`: for each core
question, `n_applies_true`, `n_clusters`, and `clusters`. Each cluster has `candidate_name`, `n_instances`,
`example_quotes`, `member_unit_ids`, and `status`. BENEFICIARY and MECHANISM were recoded by hand and carry a
`recoding_note`.

## `analysis/networks/intertextual_v0.json`: citation network

`nodes` (66): `id`, `label`, `date`, `genre`, `speaker`, `family`, `term_status`, `in_degree`.
`edges` (115): `source`, `target`, `type` (`reference`, `echo`, or `supersession`), `count`, and `evidence`
(the text that supports the link, so each edge can be audited).

## `analysis/queries/`

| File | Fields |
|---|---|
| `echo_phrases.csv` | `family`, `gov_doc`, `company_doc`, `n_words`, `phrase`, `published_first`, `formulaic` |
| `term_counts.csv` | `doc_id`, `genre`, `speaker`, `family`, `n_nominal`, `n_variant`, `n_distributive`, `nominal_forms` |
| `agency_by_genre.csv` | `genre`, `explicit_agent`, `agentless_passive`, `nominalisation` |
| `zero_count_by_genre.csv`, `nominal_by_gdstier.csv` | `genre` or `gds_tier`, then `docs_present`, `docs_variant`, `docs_absent`, `total_nominal_mentions`, `total_variant_mentions` |

## `analysis/qa/dissertation_numbers.md`

One row per reported figure: where it appears, what it is, the value in the dissertation text, the value
recomputed from the data, and `ok` when they agree.
