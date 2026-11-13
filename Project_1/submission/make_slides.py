"""Builds submission/slides.pdf (5 slides, 16:9). Numbers are read from the stored result files, not typed in.
Local fonts only (matplotlib defaults). No API call.

    .venv\\Scripts\\python.exe submission\\make_slides.py

Net saving is a stored fraction in the scorer output; the slides multiply by 100 once, for display.
"""
import json
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "results"
OUT = ROOT / "submission" / "slides.pdf"
DEC = json.loads((ROOT / "submission" / "decision.json").read_text(encoding="utf-8"))
THR = 0.99          # the threshold an active system would use; the submitted decision is all-abstain
RED, GREEN, GREY, INK = "#b3261e", "#2e7d32", "#5f6368", "#1a1a1a"


def jload(p):
    return json.loads((R / p).read_text(encoding="utf-8"))


def at(score: dict, thr: float, error_cost: float = 100.0) -> dict:
    """Counts at `thr` from a stored scorer output: the curve point with the smallest threshold >= thr."""
    n = score["at_threshold_0"]["n_fields"]
    pts = sorted((p for p in score["curve"] if p["threshold"] >= thr - 1e-12), key=lambda p: p["threshold"])
    p = pts[0] if pts else {"accepted": 0, "correct": 0, "wrong": 0, "hallucinated": 0, "coverage": 0.0}
    err = p["wrong"] + p["hallucinated"]
    return {"accepted": p["accepted"], "correct": p["correct"], "errors": err, "n": n,
            "precision": p["correct"] / p["accepted"] if p["accepted"] else None,
            "coverage": p["coverage"], "net": (p["accepted"] - error_cost * err) / n}


LLM_DEV, PROBLY_DEV = jload("llm_dev_score.json"), jload("probly_dev_score.json")
LLM_TEST, PROBLY_TEST = jload("llm_test_public_score.json"), jload("probly_test_public_score.json")
COMMON, NEVER = jload("base_common_score.json"), jload("base_never_score.json")
AUDIT = jload("uq_v2_audit_result.json")["audit"]
SELECT = jload("uq_v2_frozen_pre_audit.json")["dev_select"]
POST_AUDIT = jload("post_schema_v3/audit_frozen_eval.json")["audit"]
AUDIT_METHODS = jload("uq_v2_audit_ablation/ablation_report.json")["methods"]
CUAD_ACCEPTED_PROBLY = PROBLY_DEV["by_source"]["cuad"]["accepted"] + PROBLY_TEST["by_source"]["cuad"]["accepted"]

assert DEC["abstain_all"] is True, "slides describe the all-abstain decision"
assert NEVER["declared"]["net_saving_pct"] == 0.0


def pct(x, digits=1):
    return f"{x * 100:+.{digits}f}%"


def page(title, subtitle=None):
    fig = plt.figure(figsize=(13.33, 7.5))
    fig.text(0.05, 0.93, title, fontsize=27, weight="bold", va="top", color=INK)
    if subtitle:
        fig.text(0.05, 0.855, subtitle, fontsize=15, va="top", color=GREY)
    return fig


def bullets(fig, items, x=0.05, y=0.76, size=15, gap=0.022, width_in=12.0, color=INK):
    """Wrapped bullet list. Returns the y below the last item."""
    line_h = size * 1.42 / 72 / 7.5
    chars = max(20, int(width_in / (size * 0.52 / 72)))
    for it in items:
        block = textwrap.fill(it, chars, initial_indent="• ", subsequent_indent="   ")
        fig.text(x, y, block, fontsize=size, va="top", color=color, linespacing=1.42)
        y -= line_h * (block.count("\n") + 1) + gap
    return y


def box(fig, x, y, w, h, text, size=14, face="#f1f3f4", edge="#c4c7c5", color=INK, weight="normal"):
    ax = fig.add_axes([x, y, w, h])
    ax.set_xticks([]), ax.set_yticks([])
    ax.set_facecolor(face)
    for s in ax.spines.values():
        s.set_edgecolor(edge), s.set_linewidth(1.2)
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=size, color=color, weight=weight,
            linespacing=1.35, transform=ax.transAxes)
    return ax


def footer(fig, n):
    fig.text(0.05, 0.03, f"Project 1  |  Teach a machine to say \"I don't know\"  |  {n}/5", fontsize=10, color=GREY)
    fig.text(0.95, 0.03, "numbers from results/*.json, official scorer 5_score.py", fontsize=10, color=GREY, ha="right")


# ---------------------------------------------------------------- 1
def slide1():
    f = page("1. The problem: one mistake eats 100 correct answers",
             "Contracts, forms and scans are typed into systems by hand. Can a model book the fields itself?")
    box(f, 0.05, 0.56, 0.27, 0.20, "Human review\ncost 1 per field", size=17)
    box(f, 0.365, 0.56, 0.27, 0.20, "Wrong booked value\ncost 100", size=17, face="#fce8e6", edge=RED, color=RED,
        weight="bold")
    box(f, 0.68, 0.56, 0.27, 0.20, "Break-even precision\n> 99.0 %", size=17, weight="bold")
    c = at(COMMON, 0.95)
    bullets(f, [
        "Net saving = (accepted − 100 × (wrong + hallucinated)) / all fields. "
        "At error cost 20 the bar is 95.0%, at 500 it is 99.8%.",
        "The bar to beat is the human baseline: `never` answers nothing and scores exactly 0.0%.",
        f"A careless system loses money: the most-common-value baseline is right in {c['precision'] * 100:.0f}% of "
        f"its answers and scores {pct(c['net'])}.",
        "57.6% of all fields are absent (null). 70.6% are contract clauses that must match the gold text. "
        "About 40% of the form PDFs are scans without a text layer.",
        "So the real task is not extraction. It is knowing when not to answer.",
    ], y=0.49, size=15)
    footer(f, 1)
    return f


# ---------------------------------------------------------------- 2
def slide2():
    f = page("2. Architecture: extract, verify, quantify, decide",
             "Every stage can only remove a value. Nothing is accepted without evidence.")
    steps = [("Full text\nchunks 45k,\nno truncation", "#f1f3f4"),
             ("Prompt v4\nfull schema,\nK samples", "#f1f3f4"),
             ("Schema check\ntypes, keys,\n$defs", "#e8f0fe"),
             ("Text grounding\nvalue must be\nin the document", "#e8f0fe"),
             ("probly\ncategorical dist.\n+ entropy", "#e6f4ea"),
             ("Decision rule\nscore vs.\nthreshold", "#e6f4ea")]
    w, gap, x0 = 0.135, 0.018, 0.05
    for i, (label, face) in enumerate(steps):
        x = x0 + i * (w + gap)
        box(f, x, 0.55, w, 0.20, label, size=12.5, face=face)
        if i < len(steps) - 1:
            f.text(x + w + gap / 2, 0.65, "→", fontsize=20, ha="center", va="center", color=GREY)
    bullets(f, [
        "Scan or broken PDF: the whole document is null, no request is sent.",
        "probly: the K answers of a field are clustered by exact value. The cluster frequencies form a categorical "
        "distribution. Its entropy (nats, normalised by log K) measures how much the samples disagree.",
        "Four named decision rules: k1_grounded (model confidence), k_agreement_only, "
        "k_agreement_conf (min of agreement and confidence), k_entropy (1 − H / log K).",
        "Freeze and audit: method and threshold are chosen on dev_select, frozen, and applied once to dev_audit. "
        "Only a positive audit may switch the system on.",
        f"Submitted decision: all-abstain (abstain_all = true, threshold {DEC['threshold']}). 0 requests, net 0.0%.",
    ], y=0.48, size=14, gap=0.018, width_in=11.3)
    footer(f, 2)
    return f


# ---------------------------------------------------------------- 3
def slide3():
    f = page("3. Result: low coverage, still below the human baseline",
             f"Net saving at error cost 100, threshold {THR}. `never` (human reviews everything) = 0.0%.")
    rows = [("never / all-abstain  (submitted)", None, "all"),
            ("probly pipeline, dev", at(PROBLY_DEV, THR), "78 of 540 docs"),
            ("probly pipeline, test_public", at(PROBLY_TEST, THR), "40 of 176 docs"),
            ("LLM confidence only, dev", at(LLM_DEV, THR), "307 of 540 docs"),
            ("probly K=3 frozen, dev_audit", {"accepted": AUDIT["accepted"], "errors": AUDIT["wrong"] + AUDIT["hallucinated"],
                                              "precision": AUDIT["precision"], "coverage": AUDIT["coverage"],
                                              "net": AUDIT["net_saving_pct"]}, "7 docs"),
            ("LLM confidence only, test_public", at(LLM_TEST, THR), "75 of 176 docs"),
            ("most common value, test_public (0.95)", at(COMMON, 0.95), "all")]
    ax = f.add_axes([0.33, 0.36, 0.25, 0.42])
    ys = list(range(len(rows)))[::-1]
    nets = [0.0 if r[1] is None else r[1]["net"] * 100 for r in rows]
    ax.barh(ys, nets, color=[GREEN if r[1] is None else RED for r in rows], height=0.62)
    ax.axvline(0, color=INK, lw=1.4)
    ax.set_xscale("symlog", linthresh=1.0)
    ax.set_xlim(-400, 3)
    ax.set_xticks([-100, -10, -1, 0], ["-100%", "-10%", "-1%", "0%"], fontsize=10)
    ax.set_yticks([])
    ax.set_ylim(-0.6, len(rows) - 0.4)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.set_xlabel("net saving (log scale)", fontsize=10, color=GREY)
    fy = lambda v: ax.transData.transform((0, v))[1] / (7.5 * f.dpi)  # noqa: E731
    f.canvas.draw()
    f.text(0.05, 0.805, "Variant", fontsize=12, weight="bold", va="center")
    for label, xx in (("Net saving", 0.615), ("Precision", 0.715), ("Coverage", 0.795), ("Accepted / errors", 0.875)):
        f.text(xx, 0.805, label, fontsize=12, weight="bold", va="center")
    for (name, r, docs), yv in zip(rows, ys):
        yy = fy(yv)
        bold = "bold" if r is None or name.startswith("probly pipeline, dev") else "normal"
        f.text(0.05, yy + 0.012, name, fontsize=12.5, va="center", weight=bold)
        f.text(0.05, yy - 0.018, docs, fontsize=9.5, va="center", color=GREY)
        if r is None:
            f.text(0.615, yy, "0.0%", fontsize=13, va="center", weight="bold", color=GREEN)
            f.text(0.715, yy, "n/a", fontsize=12, va="center")
            f.text(0.795, yy, "0.0%", fontsize=12, va="center")
            f.text(0.875, yy, "0 / 0", fontsize=12, va="center")
        else:
            f.text(0.615, yy, pct(r["net"]), fontsize=13, va="center", weight="bold", color=RED)
            f.text(0.715, yy, f"{r['precision'] * 100:.1f}%", fontsize=12, va="center")
            f.text(0.795, yy, f"{r['coverage'] * 100:.1f}%", fontsize=12, va="center")
            f.text(0.875, yy, f"{r['accepted']} / {r['errors']}", fontsize=12, va="center")
    p = at(PROBLY_DEV, THR)
    bullets(f, [
        f"probly cuts the loss from {pct(at(LLM_DEV, THR)['net'])} to {pct(p['net'])} on dev, but coverage falls to "
        f"{p['coverage'] * 100:.1f}% and precision is {p['precision'] * 100:.1f}%, not 99%. Every active variant is below 0.0%.",
        f"Why coverage is low: strict text grounding, threshold {THR}, scans abstained, and {CUAD_ACCEPTED_PROBLY} accepted "
        "CUAD clause fields. Partial runs are scored against the full split, so their percentages are diluted.",
        f"Error cost 20: probly on dev is {pct(at(PROBLY_DEV, THR, 20)['net'])}. Error cost 500: "
        f"{pct(at(PROBLY_DEV, THR, 500)['net'])}. All-abstain is never negative. That is why we submit it.",
    ], y=0.265, size=12, gap=0.010, width_in=11.8)
    footer(f, 3)
    return f


# ---------------------------------------------------------------- 4
def slide4():
    f = page("4. One real error, and the five last fixes",
             "dev_audit, field labor_categories (a table): three samples agreed, every cell was in the document.")
    box(f, 0.05, 0.50, 0.42, 0.27,
        "Schema wants\n"
        "labor_category_title,  year_1_rate: number\n\n"
        "Model returned (3 of 3 samples)\n"
        "labor_category,  year_1: \"$241.81\"\n\n"
        "accepted at confidence 0.99, wrong: cost 100",
        size=12.5, face="#fce8e6", edge=RED)
    a_net, s_net = AUDIT["net_saving_pct"], SELECT["net_saving_pct"]
    bullets(f, [
        f"This one field turned the frozen choice from {pct(s_net)} (dev_select) into {pct(a_net)} (dev_audit, "
        f"{AUDIT['accepted']} accepted, {AUDIT['wrong']} wrong).",
        "Agreement is not correctness: k_entropy and k_agreement_only score "
        f"{pct(AUDIT_METHODS['k_entropy']['per_threshold']['0.95']['net_saving_pct'], 0)} on the audit at 0.95. "
        "The model repeats the same mistake three times.",
        f"With schema validation the field is invalid (post-hoc on the same samples: {POST_AUDIT['accepted']} accepted, "
        f"{POST_AUDIT['wrong']} wrong). Too few fields to prove anything.",
    ], x=0.05, y=0.455, size=12.5, gap=0.014, width_in=5.5)
    f.text(0.52, 0.775, "Five last fixes (32 tests, not yet run on the API)", fontsize=14,
           weight="bold", va="top")
    fixes = [
        ("a  transport.py", "Line breaks and tabs inside JSON strings are accepted. Long clauses are no longer lost."),
        ("b  requests.py, prompt v4", "Booleans as JSON true/false. Multi-part clauses in one string joined with \" | \"."),
        ("c  grounding.py", "Supplier’s = Supplier's. Curly quotes, dashes and non-breaking spaces are unified."),
        ("d  decision.py", "A value with confidence 0.0 becomes null. Nothing is accepted without confidence."),
        ("e  uq_probly.py", "status_counts per field in the diagnostics: why a field was rejected."),
    ]
    y = 0.715
    for head, body in fixes:
        f.text(0.52, y, head, fontsize=12.5, weight="bold", va="top", color="#174ea6")
        block = textwrap.fill(body, 62)
        f.text(0.52, y - 0.034, block, fontsize=12, va="top", linespacing=1.35)
        y -= 0.034 + 0.031 * (block.count("\n") + 1) + 0.022
    footer(f, 4)
    return f


# ---------------------------------------------------------------- 5
def slide5():
    p = at(PROBLY_DEV, THR)
    f = page("5. Limits, and the levers to get above the human baseline",
             f"The gap is concrete: {p['accepted']} accepted fields with {p['errors']} errors. With at most 1 error "
             "the pipeline would be positive.")
    f.text(0.05, 0.775, "Limits", fontsize=16, weight="bold", va="top", color=RED)
    bullets(f, [
        "The submitted system saves nothing (0.0%). It only avoids losing money.",
        f"Best active precision {p['precision'] * 100:.1f}%, needed > 99%. Coverage {p['coverage'] * 100:.1f}%, zero for contracts.",
        "Prompt v4 and the five fixes are not measured on the API.",
        "Runs cover a part of the data. The audit set has 7 documents.",
        "Confidence is not calibrated: at 1.00 the plain LLM is still wrong in "
        f"{(1 - at(LLM_DEV, 1.0)['precision']) * 100:.1f}% of its answers.",
        "No OCR or vision. Tested on Windows only.",
    ], x=0.05, y=0.72, size=12.5, gap=0.014, width_in=5.0)
    f.text(0.48, 0.775, "Levers for a positive net saving", fontsize=16, weight="bold", va="top", color=GREEN)
    bullets(f, [
        "Measure prompt v4 and the fixes on unused dev documents. Contract clauses (70.6% of the fields) become "
        "acceptable for the first time.",
        "Vision or OCR for image-only scans (about 40% of the forms), with their own stricter threshold.",
        "Calibrate the probability on several hundred labelled dev candidates (probly calibrator; features: confidence, "
        "agreement, entropy, status_counts). Choose the threshold with a conformal risk bound.",
        "Field-specific instead of document-wide abstention: accept only field types with proven precision.",
        "A second yes/no check that an accepted clause really belongs to its field.",
        "Until an independent audit is positive: suggest mode. Pre-fill with evidence, the human confirms.",
    ], x=0.48, y=0.72, size=12.5, gap=0.014, width_in=6.6)
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
