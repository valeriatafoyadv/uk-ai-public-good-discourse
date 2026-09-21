# Phase 3 -- Model evaluation (Ollama Cloud)
Run date: 2026-08-29

## Candidates tested
The 4 model names suggested in the original plan (`deepseek-v3.1:671b-cloud`, `kimi-k2:1t-cloud`, `qwen3-coder:480b-cloud`, `glm-4.6:cloud`) no longer exist in the Ollama Cloud catalogue current as of the run date (2026-08-29) -- `ollama pull` returned `pull model manifest: file does not exist` for all 4. The current catalogue was resolved against `ollama.com/search?c=cloud` and each placeholder was substituted with the current generation of the same provider/family:

| Original placeholder | Current substitute tested |
|---|---|
| `glm-4.6:cloud` | `glm-5.3:cloud` |
| `kimi-k2:1t-cloud` | `kimi-k3:cloud` |
| `deepseek-v3.1:671b-cloud` | `deepseek-v4-flash:cloud` |
| `qwen3-coder:480b-cloud` | not available (`qwen3.5:*-cloud` pull failed; omitted) |

`gpt-oss:120b-cloud` (already-tested baseline) is retained as a candidate.
All 4 evaluated candidates were verified with a short `/api/generate` call before the full run.

**Parsing note.** Several models (notably `kimi-k3:cloud` and `glm-5.3:cloud`) wrap their JSON output in ```` ```json ... ``` ```` markdown fences even though the call requests `format: "json"`. The metrics below use a parser that strips such fences (and falls back to extracting the outermost `{...}` span) before validating JSON -- this materially changes the ranking versus a naive `json.loads`, since it recovers responses that were otherwise well-formed. `scripts/05_code.py` uses the same tolerant parser for Round 1 coding.

## Metrics per model (6 units x 11 questions = 66 calls/model)
| Model | % valid JSON | % verbatim fidelity (quotes OK / total quotes) | applies=true | applies=false | errors | mean time (s) |
|---|---|---|---|---|---|---|
| gpt-oss:120b-cloud | 98.5% | 82.8% (130/157) | 54 | 11 | 1 | 8.5 |
| glm-5.3:cloud | 86.4% | 91.3% (355/389) | 51 | 6 | 9 | 55.4 |
| kimi-k3:cloud | 100.0% | 97.6% (371/380) | 58 | 8 | 0 | 35.8 |
| deepseek-v4-flash:cloud | 100.0% | 87.2% (156/179) | 44 | 22 | 0 | 8.6 |

## Reasonable applies=false on short passages (<700 characters)
| Model | applies=false / calls on short passages |
|---|---|
| gpt-oss:120b-cloud | 2/11 |
| glm-5.3:cloud | 1/11 |
| kimi-k3:cloud | 1/11 |
| deepseek-v4-flash:cloud | 4/11 |

## Decision
**Winning model: `kimi-k3:cloud`** (verbatim fidelity 97.6%, valid JSON 100.0%). Rule applied: verbatim fidelity wins (predefined decision criterion); ties are broken by % of valid JSON. The margin over the runner-up is decisive (kimi-k3:cloud at 97.6% vs. the next best at 91.3%), so the JSON-validity tiebreak is not actually needed here. Provider: Ollama Cloud. Decision date: 2026-08-29. This text can be cited almost verbatim in the methods chapter.

**Speed caveat (operational, not part of the decision rule).** `kimi-k3:cloud` is markedly slower than the alternatives (mean 35.8s/call vs. 8.5-8.6s/call for `gpt-oss:120b-cloud` and `deepseek-v4-flash:cloud`), consistent with it being a reasoning/thinking model. This does not affect the model choice (the decision rule is fidelity-first) but materially affects Round 1 runtime and is noted here for planning purposes.

Scope note: agreement with the author on the sample (Phase 3, item 4 of the PLAN) is still pending -- this report only covers the automatic metrics (valid JSON, verbatim fidelity, reasonable applies=false). Human adjudication happens in the 15-20% validation of Phase 4.

## Operational addendum (2026-08-30)

Round 1 execution was completed with **two models for cost reasons, with full
per-record traceability**: `kimi-k3:cloud` (the Phase 3 winner) coded the first
182 unit x question pairs (99.8% verbatim fidelity on its records) until the
free-tier session quota and a USD 5 extra-usage credit were exhausted — its
reasoning ("thinking") output made per-call cost several times the original
estimate. The remaining pairs were coded with `deepseek-v4-flash:cloud`
(runner-up on JSON validity at 100%, verbatim fidelity 87.2% in Phase 3;
~4x cheaper and faster), chosen to stay within the account's weekly usage cap.
Every Round 1 record carries its `model` field, failed verbatim quotes are
flagged (`quote_verified=false`) rather than silently kept, and the author's
15-20% validation sample stratifies across both models. The winning-model
decision above stands as the fidelity-first result; this addendum records the
operational deviation and its safeguards.
