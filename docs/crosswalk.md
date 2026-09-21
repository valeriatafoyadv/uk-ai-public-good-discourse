# Dissertation crosswalk

Each row links something the dissertation reports to the file that holds its data and the script that
produces it. Section numbers refer to the dissertation.

## Chapter 3: Methodology

| Reported | Value | Data file | Produced by |
|---|---|---|---|
| 3.4 Corpus size and genres | 66 documents: 9 strategy, 9 memoranda, 12 company press releases, 7 government press releases, 21 blog posts, 7 written ministerial statements, 1 regulatory response | `data/manifest.csv` | `01_manifest.py` |
| 3.4 Admission rules | window, voice, remit, blog and scrutiny rules | none (rules in `docs/pipeline.md`) | applied by `add_document.py` |
| 3.4 Text of each document | structured blocks | `data/text/*.json`, `data/raw/*.meta.json` | `02a_fetch_gov.py`, `02b_fetch_companies.py`, `03_qa_merge.py` |
| 3.5 Coding units | 91 units | `coding/units.jsonl` | `04_segment.py` |
| 3.5 Coding questions and prompts | eleven questions | `coding/prompts/prompts_v1.yaml` | written by hand, versioned |
| 3.6 Model choice | `kimi-k3:cloud`, 97.6% verbatim fidelity | `coding/model_eval/decision.md`, `results.csv` | `coding/model_eval/run_eval.py` |
| 3.6 Records and engines | 2,711 extracts; 1,175 / 1,217 / 319 by engine | `coding/round1/*.jsonl` | `05_code.py` |
| 3.6 Quotation check | 2,682 of 2,711 verbatim | `coding/round1/*.jsonl` (`quote_verified`) | `05_code.py` |
| Table 2, Round 1.2 | procedure, material coded, validity check | `coding/round1/` | `05_code.py` |
| Table 2, Rounds 1.1, 2.1, 2.2 | the author's NVivo coding | not in the repository | the author, in NVivo |

## Chapter 5: Findings

| Reported | Value | Data file | Produced by |
|---|---|---|---|
| 5.1 Partnership families | 24 documents in eight families; 42 with none | `data/manifest.csv` | `01_manifest.py` |
| 5.1 Term status | present 16, variant 7, absent 43; all nine memoranda absent | `data/manifest.csv`, `analysis/queries/term_counts.csv` | `04_segment.py` |
| 5.3 BENEFICIARY | 284 instances, 10 hand-recoded categories (321 labels) | `coding/guidebook_draft.yaml` | `05_code.py`, `06_consolidate.py`, then recoded by hand |
| 5.3 MECHANISM | 204 instances; 123 clusters, 13 with more than one instance | `coding/guidebook_draft.yaml` | `05_code.py`, `06_consolidate.py`, then recoded by hand |
| 5.4 NATURALISED_ORDER | 182 instances; 137 clusters | `coding/guidebook_draft.yaml` | `06_consolidate.py` |
| 5.5 ACTANTS | 204 instances; 27 clusters, largest 171 | `coding/guidebook_draft.yaml` | `06_consolidate.py` |
| 5.6.1 Citation network, Figure 3 | 66 nodes, 115 links (99 reference, 15 echo, 1 supersession) | `analysis/networks/intertextual_v0.json` | `06_network_v0.py` |
| 5.6.1 Most-cited documents | Action Plan 25, Blueprint 14, Playbook 8, State of Digital Government Review 7 | `analysis/networks/intertextual_v0.json` | `06_network_v0.py` |
| 5.6.1 Echo phrases by family | OpenAI 5, DeepMind 4, Anthropic 2, NVIDIA 1, Cohere 1, Cisco 1, ElevenLabs 1 | `analysis/queries/echo_phrases.csv` | `07_echo.py` |
| 5.6.2, Table 9 AGENCY by genre | 408 instances by genre and form | `analysis/queries/agency_by_genre.csv` | `11_agency_query.py` |
| 5.6.2 AGENCY shares | memoranda 86% explicit agent; strategy papers 55% and 32% nominalisation | `analysis/queries/agency_by_genre.csv` | `11_agency_query.py` |
| 5.6.2 MODALITY | 378 instances; 268 epistemic, 110 deontic; by document group | `coding/round1/*.jsonl` | tabulated directly from the records (`question = MODALITY`); no script |
| 5.6.2 Memoranda facts | shared phrases, named bodies, narrative instances | `data/text/`, `coding/round1/` | counted from the texts and records; no script |

## Chapter 6 and Appendices

| Reported | Data file | Produced by |
|---|---|---|
| 6, metaphors mentioned as a resource | the METAPHOR records in `coding/round1/` (419 distinct expressions, not analysed) | `06_consolidate.py` writes a report when run |
| Table 7 and 8, definitional sites and the umbrella term by date | `coding/round1/definitional_instances.jsonl`, `analysis/queries/term_counts.csv` | extracted by `05_code.py`; the tables are selected and written by the author |
| Appendix A, corpus table | `data/manifest.csv` | formatted from the manifest |
| Appendix B, attribute register | `data/manifest.csv` | counted from the manifest |
| Appendix C, NVivo memos | not in the repository | the author, in NVivo |
| Appendix D, reproducibility | this repository | see `docs/pipeline.md` |
| Appendix F and G, AI terms and the umbrella term | `data/text/` and the definitional records | compiled by a scan of the texts and the author's reading; no script in the repository |
| Appendix H, codebook clusters | `coding/guidebook_draft.yaml` | formatted from the guidebook |
| Figures 1 and 2 | not data | drawn for the dissertation |
| Figure 3 | `analysis/networks/intertextual_v0.json` | drawn from the network file; the interactive version is `analysis/networks/authorship_family_map.html` |

## Not in the repository

- The NVivo project, the analytical memos (D1 to D36), and the author's manual coding.
- The original PDF and HTML files of the 66 documents (only source URL, hash, and retrieval record).
- The selection spreadsheet used by `01_manifest.py`.
- The drawing code for the figures and the formatting code for the appendix tables.
