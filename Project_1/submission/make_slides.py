"""Builds submission/slides.pdf (5 slides, 16:9) from the measured score files. Local fonts only (matplotlib defaults).

    .venv\\Scripts\\python.exe submission\\make_slides.py
"""
import json
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "submission" / "slides.pdf"
DEC = json.loads((ROOT / "submission" / "decision.json").read_text(encoding="utf-8"))


def load_net(name, costs=(20, 100, 500)):
    vals = []
    for c in costs:
        d = json.loads((ROOT / "results" / f"{name}_e{c}.json").read_text(encoding="utf-8"))["declared"]
        vals.append(d["net_saving_pct"] * 100)
    return vals


ACTUAL = load_net("final_dev_score_actual")
ABSTAIN = load_net("final_dev_score_allabstain")


def page(title):
    fig = plt.figure(figsize=(13.33, 7.5))
    fig.text(0.05, 0.92, title, fontsize=26, weight="bold", va="top")
    return fig


def wrapped(text, width_in, size):
    """Wrap to the available width. A 16:9 slide is 13.33 in wide; average glyph width is about 0.55 em."""
    chars = max(20, int(width_in / (size * 0.55 / 72)))
    return textwrap.fill(text, chars, subsequent_indent="   ")


def bullets(fig, items, x=0.05, y=0.80, size=15, gap=0.072, width_in=12.0):
    line_h = size * 1.45 / 72 / 7.5  # figure height is 7.5 in
    for it in items:
        block = wrapped(it, width_in, size)
        fig.text(x, y, block, fontsize=size, va="top")
        y -= line_h * (block.count("\n") + 1) + (gap - line_h)
    return y


def footer(fig, n):
    fig.text(0.05, 0.03, f"Project 1 - uncertainty-aware extraction   |   {n}/5", fontsize=10, color="#555")


def slide1():
    f = page("1. Problem and cost")
    bullets(f, [
        "Forms and contracts must be typed into systems of record by hand.",
        "A human review costs 1 per field. A wrong value that is booked costs 100.",
        "So auto-booking pays only if it is right more than 99 percent of the time",
        "(break-even (E-1)/E = 99% at E = 100; 95% at E = 20; 99.8% at E = 500).",
        "The dev set is mostly empty: 57.6% of the fields are null (absent).",
        "Hallucinating a value for an absent field is the expensive mistake.",
    ])
    footer(f, 1)
    return f


def slide2():
    f = page("2. Pipeline (implemented, tested with mocks)")
    bullets(f, [
        "1. Full text, never truncated (CUAD and PDF text layer). Unreadable PDF -> null, no request.",
        "2. Chunks of 45,000 characters with 3,000 overlap, every field in batches of at most 10.",
        "3. Parallel-ready jobs, shared 429 stop, one retry, 60 s wait budget, reply cache.",
        "4. Merge chunks per sample: conflicting values -> null, span pieces joined with ' | '.",
        "5. Policy per sample: evidence must occur in the text; confidence must be finite in [0,1].",
        "6. probly: categorical distribution over sample answers, entropy in nats (diagnostic).",
        "7. Decision: tie or null winner -> null; otherwise min(agreement, lowest model confidence).",
        "8. Threshold chosen only on dev_cal with the official scorer; all-abstain if no saving.",
    ], size=14, gap=0.08)
    footer(f, 2)
    return f


def slide3():
    f = page("3. Measured result (6 dev_cal documents, K=1)")
    ax = f.add_axes([0.07, 0.14, 0.48, 0.62])
    xs = [0, 1, 2]
    w = 0.38
    ax.bar([x - w / 2 for x in xs], ACTUAL, w, label="model, threshold 0.95", color="#c0504d")
    ax.bar([x + w / 2 for x in xs], ABSTAIN, w, label="all-abstain (decision)", color="#4f81bd")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(xs, ["error cost 20", "error cost 100", "error cost 500"])
    ax.set_ylabel("net saving (%)")
    ax.legend(loc="lower left", fontsize=10)
    ax.set_title("Net saving vs all-manual review, official scorer", fontsize=12)
    fig_text = (
        "Functional test, not a quality proof:\n"
        "- 6 documents, 199 fields, 1 document completed fully.\n"
        "- 4 documents abstained after API 429 (team quota shared).\n"
        "- Model: precision 50% (2 accepted, 1 wrong), coverage 3.4%.\n"
        "- Decision: all-abstain. No positive saving was shown."
    )
    f.text(0.62, 0.74, wrapped(fig_text.replace("\n", " "), 5.6, 13).replace("   ", "  "),
           fontsize=13, va="top", linespacing=1.5)
    footer(f, 3)
    return f


def slide4():
    f = page("4. Accepted and abstained examples")
    bullets(f, [
        "Accepted, correct (confidence 0.95): Document Name = 'JOINT FILING AGREEMENT'.",
        "Accepted, WRONG (confidence 0.95): Agreement Date = 'March 27, 2020'.",
        "   The gold keeps the final period: 'March 27, 2020.' The scorer's token F1 is 0.67 < 0.8.",
        "Abstained by grounding (synthetic test): value 'Invented Value' with confidence 0.99.",
        "   It does not occur in the document, so the field is null with confidence 0.0.",
        "Grounding shows that a value occurs in the text. It does not prove the right field:",
        "   a real text match in another section would still be accepted.",
    ], size=15, gap=0.085)
    footer(f, 4)
    return f


def slide5():
    f = page("5. Limits, not tested, how to run")
    bullets(f, [
        "Not done: real K=3 runs (quota), Linux run (no Linux Python here), test_public (not used).",
        "Confidence is an uncalibrated score. Entropy and agreement are diagnostics only.",
        "Document-level abstention: one incomplete sample drops all fields of that document.",
        "Strict spans cost recall; the scorer's token F1 penalises small punctuation changes.",
        "Data flow: document text and prompts go to the external LLM endpoint (see SUBMISSION.md).",
        "Run: bash run_hidden.sh <gold-free input> <fresh output>  (decision: submission/decision.json)",
    ], size=14, gap=0.085)
    footer(f, 5)
    return f


def main():
    with PdfPages(OUT) as pdf:
        for build in (slide1, slide2, slide3, slide4, slide5):
            fig = build()
            pdf.savefig(fig)
            plt.close(fig)
    print("wrote", OUT, "| decision threshold:", DEC["threshold"], "abstain_all:", DEC["abstain_all"])


if __name__ == "__main__":
    main()
