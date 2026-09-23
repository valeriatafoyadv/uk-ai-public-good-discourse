# -*- coding: utf-8 -*-
import json, csv, datetime as dt, random, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.lines import Line2D

OUT = pathlib.Path(__file__).resolve().parent
INK, INK2, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"
BLUE, ORANGE = "#2a78d6", "#eb6834"
plt.rcParams["font.family"] = "DejaVu Sans"

# ---------------- Figure 1: coding rounds (caption lives in the document text)
fig, ax = plt.subplots(figsize=(12, 6.2))
ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
boxes = [
    ((0.4, 5.6), "#e8ecf4", "Round 1.1 \u00b7 author, NVivo",
     ["Close reading against the seven core", "questions plus the definitional search.", "",
      "Applied to: documents GDS authored", "or co-authored, plus the superseded", "Generative AI Framework.", "",
      "Check: analytical memos."]),
    ((5.3, 5.6), "#dcecff", "Round 1.2 \u00b7 LLM-assisted",
     ["Same questions, plus AGENCY and", "MODALITY, extended across the corpus;", "answers clustered into a candidate",
      "codebook that the author names.", "", "Applied to: all 66 documents.", "",
      "Check: quotes verified against source."]),
    ((0.4, 1.2), "#e6f5ec", "Round 2.1 \u00b7 author, then network",
     ["Intertextuality: citation, echo and", "supersession links between documents,", "coded manually, then compared with a",
      "computed citation network.", "", "Applied to: the full corpus.", "",
      "Check: manual vs computed convergence."]),
    ((5.3, 1.2), "#fdecdc", "Round 2.2 \u00b7 author, then echo/agency",
     ["Partnership-family coding: benefits,", "mechanism, safeguards, narrative, trust;", "then echo-phrase, AGENCY and MODALITY",
      "analysis.", "", "Applied to: the 24 documents in the", "eight partnership families.",
      "Check: manual vs computed readings."]),
]
for (x, y), col, title, lines in boxes:
    ax.add_patch(FancyBboxPatch((x, y), 4.3, 3.7, boxstyle="round,pad=0.08,rounding_size=0.12",
                                linewidth=1.2, edgecolor="#4a4a4a", facecolor=col))
    ax.text(x + 0.25, y + 3.3, title, fontsize=12, fontweight="bold", color=INK)
    ty = y + 2.85
    for l in lines:
        ax.text(x + 0.25, ty, l, fontsize=9.2, color="#333333")
        ty -= 0.3


def arrow(p1, p2):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=18, linewidth=1.6, color="#4a4a4a"))


arrow((4.7, 7.45), (5.3, 7.45))
arrow((7.45, 5.6), (7.45, 4.95))
arrow((2.55, 5.6), (2.55, 4.95))
arrow((4.7, 3.05), (5.3, 3.05))
fig.tight_layout()
fig.savefig(f"{OUT}/figure1_coding_rounds.png", dpi=220, facecolor="white")
plt.close(fig)

# ---------------- Figure 2: machinery-of-government timeline
fig, ax = plt.subplots(figsize=(12, 3.9))
events = [
    ("2022", "Incubator for Automation\nand Innovation set up\n(Cabinet Office)"),
    ("Nov 2023", "Relaunched as the\nIncubator for AI (i.AI)"),
    ("Jul 2024", "GDS, CDDO and i.AI move\nfrom the Cabinet Office\nto DSIT"),
    ("Jan 2025", "GDS, CDDO, i.AI, RTAU and\nthe Geospatial team merge\ninto one \u201cGovernment Digital\nService\u201d within DSIT"),
    ("Jul 2026", "DSIT merges with the Department\nfor Business and Trade \u2192 Department\nfor Business, Innovation, Science\nand Trade"),
]
n = len(events)
ax.plot([-0.4, n - 0.6], [0, 0], color=BLUE, linewidth=3, solid_capstyle="round", zorder=1)
for i, (d, lab) in enumerate(events):
    ax.scatter([i], [0], s=130, color=BLUE, zorder=3, edgecolor="white", linewidth=1.5)
    ax.text(i, 0.16, d, ha="center", va="bottom", fontsize=10.5, fontweight="bold", color=INK)
    ax.text(i, -0.22, lab, ha="center", va="top", fontsize=9, color="#333333", linespacing=1.35)
ax.set_xlim(-0.7, n - 0.3)
ax.set_ylim(-1.5, 0.8)
ax.axis("off")
fig.tight_layout()
fig.savefig(f"{OUT}/figure2_mog_timeline.png", dpi=220, facecolor="white")
plt.close(fig)

# ---------------- Figure 3: intertextual network (date x lane)
REPO = pathlib.Path(__file__).resolve().parent.parent.parent  # repo root
net = json.load(open(REPO / "analysis" / "networks" / "intertextual_v0.json", encoding="utf-8"))
man = {r["doc_id"]: r for r in csv.DictReader(open(REPO / "data" / "manifest.csv", encoding="utf-8"))}
lane_of = {"STRAT": 3, "REG": 3, "WMS": 2, "PRGOV": 2, "BLOG": 2, "PRCO": 1, "MOU": 0}
lane_name = {3: "Strategy and\nregulation", 2: "Government statements,\npress releases, blogs",
             1: "Company\npress releases", 0: "Memoranda\nof understanding"}
random.seed(7)
pos, meta = {}, {}
for nd in net["nodes"]:
    m = man[nd["id"]]
    d = dt.date.fromisoformat(m["date"])
    g = m["genre"]
    pos[nd["id"]] = (mdates.date2num(d), lane_of[g] + random.uniform(-0.28, 0.28))
    meta[nd["id"]] = (m["side"], g, nd["in_degree"])

fig, ax = plt.subplots(figsize=(12, 6.4))
fig.patch.set_facecolor("white")
ax.set_facecolor(SURFACE)
for e in net["edges"]:
    (x1, y1), (x2, y2) = pos[e["source"]], pos[e["target"]]
    if e["type"] == "reference":
        kw = dict(color="#b9b8b0", lw=0.7, alpha=0.75, zorder=1)
        style = "-|>"
    elif e["type"] == "echo":
        kw = dict(color=INK2, lw=1.1, ls=(0, (4, 2)), zorder=2)
        style = "-"
    else:
        kw = dict(color=INK, lw=2.0, zorder=2)
        style = "-|>"
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), connectionstyle="arc3,rad=0.18",
                                 arrowstyle=style, mutation_scale=7, **kw))
for nid, (x, y) in pos.items():
    side, g, indeg = meta[nid]
    ax.scatter([x], [y], s=28 + 22 * indeg, c=BLUE if side == "Public" else ORANGE,
               marker="s" if g == "MOU" else "o", edgecolor=SURFACE, linewidth=1.6, zorder=4)
labels = {
    "2025-02-10_STRAT_GDS_AIPlaybookUKGovernment": ("AI Playbook", (14, 12)),
    "2025-01-21_STRAT_GDS_BlueprintModernDigitalGov": ("Blueprint", (-62, 14)),
    "2024-02-06_REG_DSIT_ProInnovationAIRegulation": ("Pro-innovation AI regulation", (8, 14)),
    "2025-01-21_STRAT_GDS_StateOfDigitalGovReview": ("State of Digital Govt Review", (-70, -22)),
    "2026-01-20_STRAT_GDS_RoadmapModernDigitalGov": ("Roadmap", (-20, 16)),
    "2024-01-18_STRAT_CDDO_GenerativeAIFramework": ("Generative AI Framework", (0, 16)),
}
for k, (t, o) in labels.items():
    x, y = pos[k]
    ax.annotate(t, (x, y), xytext=o, textcoords="offset points", fontsize=8.5, color=INK, ha="left", zorder=6,
                bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none", alpha=0.85))
ax.set_yticks(list(lane_name))
ax.set_yticklabels([lane_name[k] for k in lane_name], fontsize=9, color=INK2)
ax.set_ylim(-0.6, 3.6)
ax.xaxis_date()
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax.tick_params(axis="x", labelsize=9, colors=INK2)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.grid(axis="y", color="#ecebe6", lw=0.8)
ax.tick_params(axis="y", length=0)
leg = [
    Line2D([0], [0], marker="o", ls="", color=BLUE, label="Government-authored document", markersize=8),
    Line2D([0], [0], marker="o", ls="", color=ORANGE, label="Company-authored document", markersize=8),
    Line2D([0], [0], marker="s", ls="", color=INK2, label="Memorandum of understanding (square)", markersize=8),
    Line2D([0], [0], color="#b9b8b0", lw=1.2, label="Reference (93)"),
    Line2D([0], [0], color=INK2, lw=1.2, ls=(0, (4, 2)), label="Echo of six or more words (11)"),
    Line2D([0], [0], color=INK, lw=2, label="Supersession (1)"),
]
ax.legend(handles=leg, loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=3, frameon=False,
          fontsize=8.6, labelcolor=INK2)
fig.tight_layout()
fig.savefig(f"{OUT}/figure3_intertextual_network.png", dpi=220, facecolor="white")
plt.close(fig)
print("done")
