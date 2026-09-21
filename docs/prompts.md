# Prompts

The instructions the language model received in Round 1.2. They are reproduced from
[`coding/prompts/prompts_v1.yaml`](../coding/prompts/prompts_v1.yaml), which is the authoritative,
versioned file (version 1). This page exists so the coding can be replicated and checked.

The file holds only the coding instructions for the pipeline: one shared header, eleven passage-level
questions, and one document-level profile. It holds no prompt for writing, editing, or interpreting the
dissertation, and none for figures or drafts. The model locates and extracts; the author interprets.

Each call fills `{doc_context}` (the document's title, date, genre, speaker, and partnership family) and `{passage}` (the
unit text). Every returned quotation is checked against the passage; see `docs/pipeline.md`, step 5.

## Shared header

```
You are a coding assistant for a discourse analysis of UK government documents
on AI in public services (2024-2026), around the phrase "AI for the public good".
You extract; the researcher interprets. Answer ONLY from the passage given.
If the passage contains nothing relevant, return {"applies": false}.
Always return valid JSON, nothing else. Any "verbatim_quote" must be copied
EXACTLY, character for character, from the passage.
Document context: {doc_context}
Passage:
---
{passage}
---
```

## Passage-level questions

| Code | Serves | Analytical source |
|---|---|---|
| BENEFICIARY | SO1, SO2, SO3 | Analytical framework; Gee (2011) subject tool |
| MECHANISM | SO1, SO2 | Analytical framework; Gee (2011) fill-in tool |
| SAFEGUARD | SO1, SO3 | Analytical framework; Gee (2011) fill-in tool |
| RESPONSIBILITY | SO1, SO3 | Analytical framework; Gee (2011) subject tool |
| PROJECTED_FUTURE | SO1, SO2 | Jasanoff & Kim (2015): visions of desirable futures |
| ACTANTS | SO1, SO3 | Kaplan (1993): actants in a policy narrative |
| NATURALISED_ORDER | SO1, SO2 | Lears (1985): cultural hegemony; Gee (2011): figured worlds |
| AGENCY | SO3 | Fairclough (2003): agent deletion, nominalisation |
| MODALITY | SO3 | Fairclough (2003): modality |
| METAPHOR | SO1 | Lakoff & Johnson (1980); MIP (Pragglejaz 2007) |
| DEFINITIONAL | SO1 | Research design: definitional instances held separately |

### BENEFICIARY

```
Question: Who is named as beneficiary of AI / of the policy in this passage?
Return JSON: {"applies": bool, "instances": [{"beneficiary": "<who, as named>",
"verbatim_quote": "<exact text>", "noun_used": "<the noun phrase used, e.g.
'the public', 'working people', 'taxpayers', 'citizens', 'the economy'>"}],
"confidence": 0-1}
```

### MECHANISM

```
Question: Through what mechanism does benefit arise in this passage
(e.g. efficiency, productivity, personalisation, growth, better decisions)?
Return JSON: {"applies": bool, "instances": [{"mechanism": "<short label>",
"how_it_works": "<one sentence, descriptive>", "verbatim_quote": "<exact>"}],
"confidence": 0-1}
```

### SAFEGUARD

```
Question: What safeguards are attached (rules, oversight, human involvement,
security, ethics, standards)?
Return JSON: {"applies": bool, "instances": [{"safeguard": "<short label>",
"binding": "recommendation|commitment|obligation|unclear",
"verbatim_quote": "<exact>"}], "confidence": 0-1}
```

### RESPONSIBILITY

```
Question: To whom is responsibility for delivery assigned?
Return JSON: {"applies": bool, "instances": [{"responsible": "<who>",
"for_what": "<short>", "verbatim_quote": "<exact>"}], "confidence": 0-1}
```

### PROJECTED_FUTURE

```
Question: What future does the passage project (the desirable state it
invites the reader to expect or pursue)?
Return JSON: {"applies": bool, "instances": [{"future": "<one sentence>",
"temporal_marker": "<e.g. 'by 2030', 'will', 'now', none>",
"verbatim_quote": "<exact>"}], "confidence": 0-1}
```

### ACTANTS

```
Question: Who or what is cast as hero, threat, or obstacle in this passage?
Return JSON: {"applies": bool, "instances": [{"actant": "<who/what>",
"role": "hero|threat|obstacle", "threat_type":
"riesgo_tecnologico|rezago_geopolitico|statu_quo_burocratico|desconfianza_publica|otro|n/a",
"verbatim_quote": "<exact>"}], "confidence": 0-1}
```

### NATURALISED_ORDER

```
Question: What social order does the passage naturalise — what arrangement
of roles, powers or relations is presented as normal, inevitable or beyond
question (rather than argued for)?
Return JSON: {"applies": bool, "instances": [{"order": "<one sentence,
descriptive: what is taken for granted>", "verbatim_quote": "<exact>"}],
"confidence": 0-1}
```

### AGENCY

```
Question: For the main claims in this passage, how is agency handled?
Return JSON: {"applies": bool, "instances": [{"form":
"agente_explicito|pasiva_sin_agente|nominalizacion",
"agent_if_named": "<who or null>", "verbatim_quote": "<exact>"}],
"confidence": 0-1}
```

### MODALITY

```
Question: What modality do the main claims carry?
deontica = must/should/commit/required; epistemica = will/could/expected/likely.
Return JSON: {"applies": bool, "instances": [{"modality": "deontica|epistemica",
"marker": "<the modal word/phrase>", "verbatim_quote": "<exact>"}],
"confidence": 0-1}
```

### METAPHOR

```
Question: Identify metaphorical expressions (MIP: the word's contextual
meaning contrasts with its basic bodily/physical meaning). For each, SUGGEST
source and target domains — the researcher will validate them.
Return JSON: {"applies": bool, "instances": [{"expression": "<exact word/phrase>",
"verbatim_quote": "<exact sentence>", "suggested_source_domain": "<e.g. MACHINE,
JOURNEY, TERRITORY, CONTAINER, FORCE>", "suggested_target_domain": "<e.g. AI,
GOVERNMENT, POLICY>", "formula": "<TARGET IS SOURCE>",
"lj_type": "estructural|orientacional|ontologica|personificacion",
"highlights": "<what the metaphor foregrounds>", "hides": "<what it backgrounds>"}],
"confidence": 0-1}
```

### DEFINITIONAL

```
Question: Does this passage EXPLICITLY state what "public good" / "public
benefit" (or close variant) means or requires? Uses without elaboration do
not count.
Return JSON: {"applies": bool, "instances": [{"defined_term": "<the phrase>",
"definition": "<what it is said to mean/require, descriptive>",
"verbatim_quote": "<exact>"}], "confidence": 0-1}
```

## Document-level profile

### DOC_PROFILE

```
You will receive the full text of one document. Answer at document level.
Return JSON: {"function": "<what the document is for, one sentence>",
"audience": "parlamento|practitioners|publico_general|industria|mixta",
"force": "recommendation|commitment|obligation|announcement",
"narrative_arc": "beginning|middle|end",
"arc_rationale": "<one sentence>"}
```

## Labels

Some answer labels were written in Spanish in the prompts (for example `agente_explicito`,
`pasiva_sin_agente`, `nominalizacion`, `deontica`, `epistemica`). `scripts/11_agency_query.py` maps the
AGENCY labels to English; see `docs/data_dictionary.md`.
