"""Builds submission/slides.pdf (5 slides, 16:9). Numbers are read from the stored result files, not typed in.
Local fonts only (matplotlib defaults).

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


def jload(p):
    return json.loads((R / p).read_text(encoding="utf-8"))


HIST_6 = {e: jload(f"final_dev_score_actual_e{e}.json")["declared"] for e in (20, 100, 500)}
SELECT = jload("uq_v2_frozen_pre_audit.json")["dev_select"]
AUDIT = jload("uq_v2_audit_result.json")["audit"]
POST_AUDIT = jload("post_schema_v3/audit_frozen_eval.json")["audit"]
HIST_METHODS = jload("uq_v2_audit_ablation/ablation_report.json")["methods"]
POST_METHODS = jload("post_schema_v3/audit_ablation/ablation_report.json")["methods"]
ORDER = ["k1_grounded", "k_agreement_only", "k_agreement_conf", "k_entropy"]


def pct(x):
    return f"{x * 100:+.1f}%"


def page(title):
    fig = plt.figure(figsize=(13.33, 7.5))
    fig.text(0.05, 0.92, title, fontsize=26, weight="bold", va="top")
    return fig


def wrapped(text, width_in, size):
    chars = max(20, int(width_in / (size * 0.55 / 72)))
    return textwrap.fill(text, chars, subsequent_indent="   ")


def bullets(fig, items, x=0.05, y=0.80, size=15, gap=0.072, width_in=12.0):
    line_h = size * 1.45 / 72 / 7.5
    for it in items:
        block = wrapped(it, width_in, size)
        fig.text(x, y, block, fontsize=size, va="top")
        y -= line_h * (block.count("\n") + 1) + (gap - line_h)
    return y


def footer(fig, n):
    fig.text(0.05, 0.03, f"Project 1 | {n}/5 | historical results are not revised; post-hoc results are marked",
             fontsize=10, color="#555")


def slide1():
    f = page("1. Problem and cost")
    bullets(f, [
        "Contracts and forms must be typed into systems of record by hand.",
        "A human review costs 1 per field. A wrong booked value costs 100.",
        "Auto-booking pays only if accepted values are right more than 99% of the time (E = 100).",
        "Break-even precision (E-1)/E: 99.0% for E = 100, 95% for E = 20, 99.8% for E = 500.",
        "The dev set is mostly empty: 57.6% of the fields are null (absent).",
        "Hallucinating a value for an absent field is the expensive mistake.",
    ])
    footer(f, 1)
    return f


def slide2():
    f = page("2. Pipeline and release rule")
    bullets(f, [
        "Full text, no truncation. Unreadable PDF -> null, no request. Chunks of 45k with 3k overlap, batches of 10 fields.",
        "Prompt v3 sends the full field schema including all $defs. Schema validity and textual evidence are checked separately.",
        "Each sample: a field is valid only if it passes both checks. Invalid values are never accepted.",
        "probly: categorical distribution over the K valid answers, entropy in nats (diagnostic and method k_entropy).",
        "Methods: k1_grounded, k_agreement_only, k_agreement_conf (min of share and confidence), k_entropy.",
        "Freeze on dev_select, audit once on dev_audit. Active only if every release criterion holds.",
        f"Current decision: {'all-abstain' if DEC['abstain_all'] else 'active'} (threshold {DEC['threshold']}).",
    ], size=14, gap=0.08)
    footer(f, 2)
    return f


def slide3():
    f = page("3. Measured results (historical, prompt v2)")
    rows = [
        ("6 dev_cal docs, K=1, thr 0.95", "199 fields", "2 acc, 1 wrong", pct(HIST_6[100]["net_saving_pct"]),
         f"error cost 20: {pct(HIST_6[20]['net_saving_pct'])}, 500: {pct(HIST_6[500]['net_saving_pct'])}"),
        ("dev_select, K=3, frozen 0.99", "164 fields", f"{SELECT['accepted']} acc, {SELECT['wrong']} wrong",
         pct(SELECT["net_saving_pct"]), f"precision {SELECT['precision'] * 100:.0f}%, coverage {SELECT['coverage'] * 100:.1f}%"),
        ("dev_audit, K=3, frozen 0.99", "130 fields", f"{AUDIT['accepted']} acc, {AUDIT['wrong']} wrong",
         pct(AUDIT["net_saving_pct"]), f"precision {AUDIT['precision'] * 100:.0f}%, coverage {AUDIT['coverage'] * 100:.1f}%"),
    ]
    y = 0.80
    for name, n, counts, net, extra in rows:
        f.text(0.05, y, f"{name}   |   {n}   |   {counts}   |   net {net}", fontsize=14, va="top", weight="bold")
        f.text(0.07, y - 0.04, extra, fontsize=12, va="top", color="#333")
        y -= 0.13
    bullets(f, [
        "Net saving = (accepted - 100 x (wrong + hallucinated)) / fields. Hallucinated values: 0 in all three sets.",
        "The sets are very small (3 to 14 accepted fields). These are limited development measurements, not quality results.",
        "Each K=3 set has 3 short CUAD contracts and 4 small ExtractBench documents (no scan).",
    ], y=0.40, size=13, gap=0.075)
    footer(f, 3)
    return f


def slide4():
    f = page("4. Audit comparison at 0.95: historical vs post-hoc")
    ax = f.add_axes([0.07, 0.16, 0.50, 0.66])
    xs = list(range(len(ORDER)))
    w = 0.38
    hist = [HIST_METHODS[m]["per_threshold"]["0.95"]["net_saving_pct"] * 100 for m in ORDER]
    post = [POST_METHODS[m]["per_threshold"]["0.95"]["net_saving_pct"] * 100 for m in ORDER]
    ax.bar([x - w / 2 for x in xs], hist, w, label="historical (prompt v2)", color="#c0504d")
    ax.bar([x + w / 2 for x in xs], post, w, label="post-hoc validation, same samples", color="#9bbb59")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(xs, ["k1_grounded", "agreement_only", "agreement_conf", "k_entropy"], fontsize=9)
    ax.set_ylabel("net saving (%)")
    ax.legend(loc="lower left", fontsize=9)
    ax.set_title("dev_audit, 130 fields, threshold 0.95", fontsize=12)
    lines = []
    for m in ORDER:
        t = POST_METHODS[m]["per_threshold"]["0.95"]
        lines.append(f"{m}: {t['accepted']} acc, {t['wrong']} wrong, {t['hallucinated']} hall")
    f.text(0.62, 0.78, "Post-hoc counts (no new API call):", fontsize=13, weight="bold", va="top")
    f.text(0.62, 0.72, "\n".join(lines), fontsize=12, va="top", linespacing=1.6)
    f.text(0.62, 0.50, "Every method is negative at 0.95 in both analyses.\n"
                       "The historical values were printed as factor 100 too small in earlier drafts.",
           fontsize=12, va="top", color="#333", linespacing=1.6)
    footer(f, 4)
    return f


def slide5():
    f = page("5. Error cause, limits and next measurement")
    bullets(f, [
        "Confirmed cause: the prompt omitted $defs, so the model invented row keys (labor_category, year_1) and currency text.",
        "Second cause: nested values were checked only for text occurrence, not for keys or types. Fixed by schema validation.",
        "Post-hoc: the wrong table value is no longer accepted. This is not a measurement of prompt v3.",
        "Not done: prompt v3 on the API, Linux run, calibration (no predictor, no training data), test_public (not used).",
        "Release rule: the 30-accepted-field minimum is a project heuristic, not a statistical result.",
        "Next: a new K=3 measurement with prompt v3 on dev documents not used before, method and threshold frozen first.",
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
