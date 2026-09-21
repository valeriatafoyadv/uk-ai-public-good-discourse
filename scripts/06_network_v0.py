"""Preliminary intertextual network (v0) -- SO2, Fairclough.

Detection of explicit references between corpus documents via curated,
lowercase title aliases. Long aliases are masked before searching for the
short ones so they aren't counted twice (e.g. "response to the AI Opportunities
Action Plan" vs "AI Opportunities Action Plan").

MoU rule: mention of "memorandum of understanding" + company name ->
reference to that family's MoU.

Output: analysis/networks/intertextual_v0.json (nodes with manifest attributes,
edges with type, count and evidence). Preliminary: the author audits the edges
with the included evidence; Phase 6 adds echoes and shared codes.
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "networks" / "intertextual_v0.json"

# alias (lowercase) -> target doc_id; match order: longest first
ALIASES = {
    "2024-01-18_STRAT_CDDO_GenerativeAIFramework": [
        "generative ai framework"],
    "2024-02-06_REG_DSIT_ProInnovationAIRegulation": [
        "pro-innovation approach to ai regulation", "ai regulation white paper",
        "pro-innovation approach to regulating ai"],
    "2025-01-13_STRAT_DSIT_AIActionPlanGovResponse": [
        "government response to the ai opportunities action plan",
        "response to the ai opportunities action plan"],
    "2025-01-13_STRAT_DSIT_AIOpportunitiesActionPlan": [
        "ai opportunities action plan"],
    "2026-01-29_STRAT_DSIT_AIActionPlanOneYearOn": [
        "ai opportunities action plan: one year on", "one year on report"],
    "2025-01-12_PRGOV_PMO_BlueprintTurbochargeAI": [
        "blueprint to turbocharge"],
    "2025-01-21_STRAT_GDS_BlueprintModernDigitalGov": [
        "blueprint for modern digital government",
        "blueprint for a modern digital government"],
    "2025-01-21_STRAT_GDS_StateOfDigitalGovReview": [
        "state of digital government review", "state of digital government"],
    "2025-02-10_STRAT_GDS_AIPlaybookUKGovernment": [
        "artificial intelligence playbook", "ai playbook"],
    "2026-01-20_STRAT_GDS_RoadmapModernDigitalGov": [
        "roadmap for modern digital government"],
    "2025-08-18_BLOG_GDS_AIExemplarsProgramme": [
        "ai exemplars programme", "ai exemplars"],
    "2025-09-16_PRCO_OpenAI_StargateUK": ["stargate uk"],
}

MOU_DOCS = {
    "Anthropic": ["2025-02-14_MOU_Anthropic_AIOpportunities"],
    "Cohere": ["2025-06-16_MOU_Cohere_AIOpportunities"],
    "OpenAI": ["2025-07-21_MOU_OpenAI_AIOpportunities"],
    "DeepMind": ["2025-12-11_MOU_DeepMind_AIOpportunitiesSecurity"],
    "ElevenLabs": ["2026-06-08_MOU_ElevenLabs_AIOpportunities"],
    "NVIDIA": ["2025-06-09_MOU_NVIDIA_AISkills", "2025-06-09_MOU_NVIDIA_AIAdvancedConnectivity"],
    "Cisco": ["2026-06-08_MOU_Cisco_AIOpportunities"],
    "Synthesia": ["2026-06-08_MOU_Synthesia_AISkillsOpportunities"],
}
COMPANY_TOKENS = {"Anthropic": ["anthropic"], "Cohere": ["cohere"],
                  "OpenAI": ["openai", "open ai"],
                  "DeepMind": ["deepmind", "google deepmind"],
                  "ElevenLabs": ["elevenlabs", "eleven labs"],
                  "NVIDIA": ["nvidia"], "Cisco": ["cisco"], "Synthesia": ["synthesia"]}

SUPERSESSION = [
    # citing (new) -> cited (retired): the Playbook supersedes the GenAI Framework
    ("2025-02-10_STRAT_GDS_AIPlaybookUKGovernment",
     "2024-01-18_STRAT_CDDO_GenerativeAIFramework"),
]


def load_text(doc_id):
    p = ROOT / "data" / "text" / f"{doc_id}.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    return "\n".join(b["text"] for b in doc["blocks"]).lower()


def snippet(text, pos, width=90):
    s = max(0, pos - width)
    return re.sub(r"\s+", " ", text[s:pos + width]).strip()


def main():
    rows = list(csv.DictReader((ROOT / "data" / "manifest.csv").open(encoding="utf-8")))
    texts = {r["doc_id"]: load_text(r["doc_id"]) for r in rows}

    # (alias, target) pairs sorted by descending length to mask long ones first
    pairs = sorted(((a, t) for t, al in ALIASES.items() for a in al),
                   key=lambda x: -len(x[0]))

    edges = []
    for r in rows:
        src = r["doc_id"]
        text = texts[src]
        masked = text
        for alias, target in pairs:
            if target == src:
                # the doc's own title: mask it so it isn't handed to shorter aliases
                masked = masked.replace(alias, "#" * len(alias))
                continue
            count, first_pos = 0, None
            while True:
                i = masked.find(alias)
                if i < 0:
                    break
                count += 1
                if first_pos is None:
                    first_pos = i
                masked = masked[:i] + "#" * len(alias) + masked[i + len(alias):]
            if count:
                edges.append({"source": src, "target": target, "type": "reference",
                              "count": count, "evidence": snippet(text, first_pos)})
        # MoU rule
        if "memorandum of understanding" in text or re.search(r"\bmou\b", text):
            for fam, mou_ids in MOU_DOCS.items():
                if r["family"] not in (fam, "None"):
                    continue
                # only within the family, or docs without a family that name the company
                if any(tok in text for tok in COMPANY_TOKENS[fam]):
                    if r["family"] == fam or src.endswith("AIAdoptionSummitPartnerships"):
                        m = re.search(r"memorandum of understanding|\bmou\b", text)
                        for mou_id in mou_ids:
                            if src == mou_id:
                                continue
                            edges.append({"source": src, "target": mou_id,
                                          "type": "reference", "count": 1,
                                          "evidence": snippet(text, m.start())})

    for a, b in SUPERSESSION:
        edges.append({"source": a, "target": b, "type": "supersession", "count": 1,
                      "evidence": "The AI Playbook supersedes the Generative AI Framework (gov.uk, 2025-02-10)."})

    # echo edges (SO3, Hajer): non-formulaic shared n-grams within each MoU family,
    # from Phase 6B output. Undirected in reading (drawn without direction weight);
    # excluded from in_degree, which measures reference authority only.
    echo_csv = ROOT / "analysis" / "queries" / "echo_phrases.csv"
    if echo_csv.exists():
        pair_stats = {}
        for row in csv.DictReader(echo_csv.open(encoding="utf-8")):
            if row.get("formulaic", "").strip().lower() in ("true", "1", "yes"):
                continue
            key = (row["gov_doc"], row["company_doc"])
            st = pair_stats.setdefault(key, {"n": 0, "max_words": 0, "phrase": ""})
            st["n"] += 1
            if int(row["n_words"]) > st["max_words"]:
                st["max_words"] = int(row["n_words"])
                st["phrase"] = row["phrase"]
        for (gov, comp), st in sorted(pair_stats.items()):
            edges.append({"source": comp, "target": gov, "type": "echo",
                          "count": st["n"],
                          "evidence": f'{st["n"]} shared n-grams; longest '
                                      f'({st["max_words"]} words): "{st["phrase"][:180]}"'})
        print(f"echo edges: {len(pair_stats)} document pairs")

    indeg = {}
    for e in edges:
        if e["type"] == "echo":
            continue
        indeg[e["target"]] = indeg.get(e["target"], 0) + e["count"]

    nodes = []
    for r in rows:
        short = r["doc_id"].split("_", 3)[-1] if not r["doc_id"].startswith("CONTEXT") \
            else r["doc_id"].split("_", 4)[-1]
        nodes.append({
            "id": r["doc_id"], "label": short, "date": r["date"],
            "genre": r["genre"], "speaker": r["speaker"], "family": r["family"],
            "term_status": r["term_status"], "in_degree": indeg.get(r["doc_id"], 0),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"nodes": nodes, "edges": edges}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(nodes)} nodes, {len(edges)} edges -> {OUT}")
    print("\nTop referenced (in-degree):")
    for n in sorted(nodes, key=lambda n: -n["in_degree"])[:10]:
        print(f"  {n['in_degree']:>3}  {n['id']}")
    print("\nEdges by type:", {t: sum(1 for e in edges if e['type'] == t)
                                for t in {e['type'] for e in edges}})


if __name__ == "__main__":
    main()
