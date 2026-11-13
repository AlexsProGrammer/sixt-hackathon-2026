"""Builds submission/slides.pdf: 5 clean 16:9 slides that present the idea and the vision.

    .venv/bin/python submission/make_slides.py

Only matplotlib, no API calls, no data folder needed. The few numbers on the slides are measured results.
Each constant below names the command that produced it, so it can be checked again.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent / "slides.pdf"

# ---------------------------------------------------------------- measured numbers (sources in comments)
# analyse_fields.py results/llm_dev.jsonl  (307 dev docs, ExtractBench answers, "source / confidence" table)
CONF_VS_TRUTH = [("model says\n0.95", 0.702), ("model says\n0.99", 0.957), ("model says\n1.00", 0.890)]
# 5_score.py on the stored runs (README / SUBMISSION results table) and the leave-one-group-out
# whitelist simulation of analyse_fields.py (min_n=3, grounded): 378 booked, 0 wrong
NET = [("Most common\nvalue", -177.8), ("Model\nconfidence", -30.9), ("Same model\n3x (probly)", -1.2),
       ("Human does\neverything", 0.0), ("Proven field\ncells", +3.0)]
SELECTOR_BOOKED, SELECTOR_WRONG = 378, 0
# vision_probe.py data/raw/extractbench/docs/short/07021-2016-p0014.pdf [model]
TEXT_LAYER = "ine Harbour Water Utillties LLC"
VISION = "Pine Harbour Water Utilities LLC"

# ---------------------------------------------------------------- style
W, H = 16, 9
INK, MUTED, LIGHT = "#1d1d1f", "#6e6e73", "#f2f2f4"
ORANGE, GREEN, RED, BLUE = "#ff5f00", "#1f9d55", "#d93025", "#1a73e8"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 16})


def slide(n, kicker, title):
    fig = plt.figure(figsize=(13.333, 7.5))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W), ax.set_ylim(0, H), ax.axis("off")
    ax.add_patch(plt.Rectangle((0, H - 0.12), W, 0.12, color=ORANGE, lw=0))
    ax.text(0.8, 8.15, kicker.upper(), fontsize=13, color=ORANGE, weight="bold", va="center")
    ax.text(0.8, 7.45, title, fontsize=30, color=INK, weight="bold", va="center")
    ax.text(0.8, 0.4, "A-Team  ·  Teach a machine to say \"I don't know\"", fontsize=10, color=MUTED)
    ax.text(W - 0.8, 0.4, f"{n} / 5", fontsize=10, color=MUTED, ha="right")
    return fig, ax


def card(ax, x, y, w, h, title=None, body=None, face=LIGHT, edge=None, tcolor=INK, tsize=17, bsize=13.5,
         center=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.18",
                                fc=face, ec=edge or face, lw=2))
    if center:
        if title:
            ax.text(x + w / 2, y + h / 2 + (0.28 if body else 0), title, fontsize=tsize, weight="bold",
                    color=tcolor, ha="center", va="center")
        if body:
            ax.text(x + w / 2, y + h / 2 - (0.32 if title else 0), body, fontsize=bsize, color=MUTED,
                    ha="center", va="center", linespacing=1.4)
        return
    if title:
        ax.text(x + 0.3, y + h - 0.45, title, fontsize=tsize, weight="bold", color=tcolor, va="center")
    if body:
        ax.text(x + 0.3, y + h - 0.95, body, fontsize=bsize, color=MUTED, va="top", linespacing=1.45)


def arrow(ax, x0, y0, x1, y1, color=MUTED, lw=2.2):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=18, color=color, lw=lw))


# ---------------------------------------------------------------- 1. the problem
def s1():
    fig, ax = slide(1, "The problem", "One confident mistake costs 100 good answers")
    outcomes = [("Send to a human", "cost 1", "the safe choice", LIGHT, INK),
                ("Book it, correct", "+1", "saves the review", "#e7f6ec", GREEN),
                ("Book it, wrong", "−100", "reaches the system of record", "#fdecea", RED)]
    for i, (title, big, sub, face, col) in enumerate(outcomes):
        x = 0.8 + i * 5.0
        card(ax, x, 3.5, 4.4, 3.0, face=face)
        ax.text(x + 2.2, 5.95, title, fontsize=19, weight="bold", color=INK, ha="center", va="center")
        ax.text(x + 2.2, 4.95, big, fontsize=38, weight="bold", color=col, ha="center", va="center")
        ax.text(x + 2.2, 4.0, sub, fontsize=14, color=MUTED, ha="center", va="center")
    ax.text(W / 2, 2.45, "Automation only pays if the booked answers are right more than 99 % of the time.",
            fontsize=19, color=INK, ha="center", weight="bold")
    ax.text(W / 2, 1.6, "The real task is not to extract more. It is to know which answers you can prove.",
            fontsize=16, color=MUTED, ha="center")
    return fig


# ---------------------------------------------------------------- 2. the insight
def s2():
    fig, ax = slide(2, "What we learned", "Models don't know when they are wrong")
    # left: confidence vs truth
    bx = fig.add_axes([0.07, 0.17, 0.40, 0.55])
    labels = [c[0] for c in CONF_VS_TRUTH]
    vals = [c[1] * 100 for c in CONF_VS_TRUTH]
    bars = bx.bar(labels, vals, color=[MUTED, MUTED, RED], width=0.6)
    bx.axhline(99, color=GREEN, lw=2.5, ls="--")
    bx.text(2.45, 99.6, "needed: 99 %", color=GREEN, fontsize=13, ha="right", va="bottom", weight="bold")
    for b, v in zip(bars, vals):
        bx.text(b.get_x() + b.get_width() / 2, v - 2.5, f"{v:.0f} %", ha="center", va="top", color="white",
                fontsize=17, weight="bold")
    bx.set_ylim(60, 103)
    bx.set_ylabel("actually correct", fontsize=13, color=MUTED)
    bx.tick_params(labelsize=13, colors=INK, length=0)
    for s in ("top", "right", "left"):
        bx.spines[s].set_visible(False)
    bx.set_yticks([])
    ax.text(0.9, 6.55, "Self-reported confidence", fontsize=17, weight="bold", color=INK)
    # right: same model three times
    card(ax, 8.6, 1.4, 6.6, 5.5, face=LIGHT)
    ax.text(8.95, 6.4, "Asking the same model 3 times", fontsize=17, weight="bold", color=INK)
    for i in range(3):
        y = 5.45 - i * 0.78
        ax.add_patch(FancyBboxPatch((8.95, y - 0.27), 5.9, 0.55, boxstyle="round,pad=0,rounding_size=0.1",
                                    fc="white", ec="#d0d0d5"))
        ax.text(9.15, y, f"sample {i + 1}:  year_1 = \"$241.81\"   conf 0.99", fontsize=12.5, color=INK,
                va="center", family="DejaVu Sans Mono")
    ax.text(8.95, 2.95, "3 of 3 agree  →  booked  →  wrong (−100)", fontsize=15, color=RED, weight="bold")
    ax.text(8.95, 2.15, "Agreement measures consistency,\nnot correctness. The model repeats its own mistake.",
            fontsize=13.5, color=MUTED, va="center", linespacing=1.45)
    return fig


# ---------------------------------------------------------------- 3. the idea
def s3():
    fig, ax = slide(3, "Our idea", "Different pipelines, different eyes, proven trust")
    card(ax, 0.6, 3.55, 2.3, 1.6, "Document", "+ schema", center=True)
    pipes = [("Contracts", "whole text, long context"), ("Clean forms", "PDF + text layer"),
             ("Scans", "PDF / page images")]
    for i, (t, b) in enumerate(pipes):
        y = 5.35 - i * 1.65
        card(ax, 3.9, y, 3.2, 1.3, t, b, center=True, face="#fff1e8", edge=ORANGE, tsize=16, bsize=12.5)
        arrow(ax, 2.9, 4.35, 3.88, y + 0.65)
        arrow(ax, 7.1, y + 0.65, 8.05, 4.35)
    ax.text(5.5, 6.95, "1  route", fontsize=13, color=ORANGE, weight="bold", ha="center")
    card(ax, 8.1, 3.3, 2.9, 2.1, "Several views", "Gemini · Claude\nPDF · text", center=True, face="#e8f0fe",
         edge=BLUE)
    ax.text(9.55, 6.95, "2  different eyes", fontsize=13, color=BLUE, weight="bold", ha="center")
    arrow(ax, 11.0, 4.35, 11.6, 4.35)
    card(ax, 11.65, 3.3, 2.0, 2.1, "probly", "agreement\n+ entropy", center=True, face="#e8f0fe", edge=BLUE)
    arrow(ax, 13.65, 4.35, 14.0, 4.35)
    ax.add_patch(plt.Polygon([[14.0, 4.35], [14.75, 5.25], [15.5, 4.35], [14.75, 3.45]], fc="#e7f6ec",
                             ec=GREEN, lw=2))
    ax.text(14.75, 4.35, "proven?", fontsize=12, ha="center", va="center", weight="bold", color=GREEN)
    ax.text(14.75, 6.95, "3  selector", fontsize=13, color=GREEN, weight="bold", ha="center")
    arrow(ax, 14.75, 5.25, 14.75, 6.0, color=GREEN)
    ax.text(14.75, 6.25, "book", fontsize=14, color=GREEN, ha="center", weight="bold")
    arrow(ax, 14.75, 3.45, 14.75, 2.7, color=MUTED)
    ax.text(14.75, 2.35, "human", fontsize=14, color=MUTED, ha="center", weight="bold")
    ax.text(0.8, 1.35, "A field is booked only if its field type has zero errors on many independent "
                       "documents\nand the views agree with evidence in the document. Everything else goes to a "
                       "human.", fontsize=14.5, color=INK, linespacing=1.5)
    return fig


# ---------------------------------------------------------------- 4. first proof
def s4():
    fig, ax = slide(4, "First proof", "Better eyes, and a selector that beats the human")
    # left: vision example
    ax.text(0.9, 6.55, "A damaged scan (Schedule K-1)", fontsize=17, weight="bold", color=INK)
    rows = [("Text layer", TEXT_LAYER, RED, "✗"), ("Gemini on PDF", VISION, GREEN, "✓"),
            ("Claude on PDF", VISION, GREEN, "✓")]
    for i, (who, val, col, mark) in enumerate(rows):
        y = 5.55 - i * 1.15
        ax.add_patch(FancyBboxPatch((0.9, y - 0.42), 6.6, 0.84, boxstyle="round,pad=0,rounding_size=0.12",
                                    fc="white", ec=col, lw=2))
        ax.text(1.15, y + 0.13, who, fontsize=11.5, color=MUTED, va="center")
        ax.text(1.15, y - 0.17, val, fontsize=14.5, color=INK, va="center", weight="bold")
        ax.text(7.15, y, mark, fontsize=24, color=col, va="center", ha="center", weight="bold")
    ax.text(0.9, 1.75, "Two model families, same correct answer:\nthat agreement is a signal worth trusting.",
            fontsize=13.5, color=MUTED, linespacing=1.45)
    # right: net saving chart
    ax.text(8.6, 6.55, "Net saving vs. human review (dev)", fontsize=17, weight="bold", color=INK)
    cx = fig.add_axes([0.62, 0.16, 0.34, 0.54])
    names = [n for n, _ in NET]
    vals = [v for _, v in NET]
    clipped = [max(v, -12) for v in vals]
    colors = [RED if v < 0 else (MUTED if v == 0 else GREEN) for v in vals]
    ys = list(range(len(NET)))[::-1]
    cx.barh(ys, clipped, color=colors, height=0.62)
    cx.axvline(0, color=INK, lw=1.5)
    for y, v, c in zip(ys, vals, clipped):
        txt = f"{v:+.1f} %" if v else "0 %"
        if v < -3:      # long red bar: label inside, at its left end
            cx.text(c + 0.3, y, txt, va="center", ha="left", fontsize=14, weight="bold", color="white")
        elif v < 0:
            cx.text(c - 0.3, y, txt, va="center", ha="right", fontsize=14, weight="bold", color=INK)
        else:
            cx.text(c + 0.3, y, txt, va="center", ha="left", fontsize=14, weight="bold", color=INK)
    cx.set_yticks(ys, names, fontsize=12.5)
    cx.set_xlim(-12.5, 6.5)
    cx.set_xticks([])
    for s in ("top", "right", "bottom", "left"):
        cx.spines[s].set_visible(False)
    cx.tick_params(length=0)
    cx.text(-12.3, -0.95, "bars clipped at −12 %", fontsize=10, color=MUTED)
    ax.text(8.6, 0.95, f"{SELECTOR_BOOKED} fields booked, {SELECTOR_WRONG} wrong (simulated on stored answers, "
                       "text-only pipeline)", fontsize=11.5, color=MUTED)
    return fig


# ---------------------------------------------------------------- 5. the vision
def s5():
    fig, ax = slide(5, "The vision", "Trust is earned per field, not granted to a model")
    steps = [("1  Suggest", "Every field is pre-filled\nwith its evidence.\nA human confirms.", "#fff1e8",
              ORANGE),
             ("2  Earn trust", "Each confirmation is a label.\nA field type with a clean\nrecord goes automatic.",
              "#e8f0fe", BLUE),
             ("3  Scale", "More document types,\nscans and contracts.\nAny drift → back to human.", "#e7f6ec",
              GREEN)]
    for i, (t, b, face, edge) in enumerate(steps):
        x = 0.8 + i * 5.0
        card(ax, x, 3.0, 4.4, 3.4, t, b, face=face, edge=edge, tcolor=edge, tsize=20, bsize=15)
        if i < 2:
            arrow(ax, x + 4.45, 4.7, x + 4.95, 4.7, color=INK)
    ax.text(W / 2, 2.15, "Measured, reversible, and safe from day one: the system never books what it cannot "
                         "prove.", fontsize=17, color=INK, ha="center", weight="bold")
    ax.text(W / 2, 1.35, "Next: frozen audit of the selector  ·  vision + 2-model views  ·  contract clauses  ·  "
                         "review dashboard", fontsize=13, color=MUTED, ha="center")
    return fig


def main():
    with PdfPages(OUT) as pdf:
        for build in (s1, s2, s3, s4, s5):
            fig = build()
            pdf.savefig(fig)
            plt.close(fig)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
