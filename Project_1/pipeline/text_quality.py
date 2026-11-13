"""Text-layer quality score (T05). Stdlib only, deterministic, never reads gold.

A damaged text layer drops or garbles glyphs ("ine Harbour Water Utillties" for "Pine Harbour Water Utilities").
Values copied from such a layer are wrong in a way that grounding cannot detect, so the router sends the document
to a route that does not trust the layer.

Features (all in [0, 1], computed on the alphabetic tokens of length >= 3, lowercased):
- dict_ratio        share of tokens found in the bundled word list (pipeline/data/words.txt)
- clipped_ratio     share of tokens that are NOT in the list but become a word after ONE leading letter is added
                    ("ine" -> "pine", "ruitland" -> "fruitland"): the signature of a dropped first glyph
- odd_char_ratio    share of non-whitespace characters outside printable ASCII (replacement characters, private use)
- engine_agreement  token Jaccard between the pdftotext and the pypdf output (None when only one engine ran)

score() combines them into one number in [0, 1]; higher is better. The threshold tau_q is tuned offline by
tools/tune_quality.py and stored in pipeline/router_config.json.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORDS_FILE = HERE / "data" / "words.txt"
SYSTEM_WORDS = Path("/usr/share/dict/words")

MIN_TOKEN = 3
_TOKEN = re.compile(r"[A-Za-z]+")
_ALPHA = "abcdefghijklmnopqrstuvwxyz"

# Weights of the combined score. score = dict_ratio - W_CLIPPED*clipped - W_ODD*odd, then scaled by the engine
# agreement and the amount of text. They were chosen on the `fit` split by tools/tune_quality.py.
W_CLIPPED = 2.0
W_ODD = 2.0
MIN_TOKENS_FULL_CONFIDENCE = 30      # fewer alphabetic tokens: the ratios are noisy, the score is scaled down


@lru_cache(maxsize=1)
def load_words() -> frozenset[str]:
    """The bundled word list. The tracked file is preferred so that scores are identical on every machine;
    /usr/share/dict/words is only a fallback when the tracked file is missing."""
    for path in (WORDS_FILE, SYSTEM_WORDS):
        try:
            words = {w.strip().lower() for w in path.read_text(encoding="utf-8", errors="ignore").splitlines()}
        except OSError:
            continue
        words = {w for w in words if w.isalpha() and len(w) >= MIN_TOKEN}
        if words:
            return frozenset(words)
    return frozenset()


def tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text) if len(t) >= MIN_TOKEN]


def _is_clipped(tok: str, words: frozenset[str]) -> bool:
    """Not a word itself, but one leading letter makes it one."""
    if tok in words:
        return False
    return any((c + tok) in words for c in _ALPHA)


def odd_char_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    odd = 0
    for c in chars:
        o = ord(c)
        if o < 127 and (o >= 32):
            continue
        # common typographic punctuation and accented Latin letters are not damage
        cat = unicodedata.category(c)
        if c in "‘’‚“”„–—−•·©®™°§€£¥…«»" or (cat.startswith("L") and o < 0x250):
            continue
        odd += 1
    return odd / len(chars)


def engine_agreement(text_a: str | None, text_b: str | None) -> float | None:
    """Token Jaccard between two extractions of the same PDF. None unless both have tokens."""
    if not text_a or not text_b:
        return None
    a, b = set(tokens(text_a)), set(tokens(text_b))
    if not a or not b:
        return None
    return len(a & b) / len(a | b)


def features(text: str | None, other_text: str | None = None, words: frozenset[str] | None = None) -> dict:
    """The raw quality features of one text layer. `other_text` is the second engine's output, when available."""
    words = load_words() if words is None else words
    toks = tokens(text or "")
    n = len(toks)
    if n:
        known = sum(1 for t in toks if t in words)
        clipped = sum(1 for t in toks if _is_clipped(t, words))
        dict_ratio, clipped_ratio = known / n, clipped / n
    else:
        dict_ratio = clipped_ratio = 0.0
    return {"n_tokens": n, "n_chars": len(text or ""), "dict_ratio": round(dict_ratio, 4),
            "clipped_ratio": round(clipped_ratio, 4), "odd_char_ratio": round(odd_char_ratio(text or ""), 4),
            "engine_agreement": (None if (a := engine_agreement(text, other_text)) is None else round(a, 4))}


def score(feats: dict, w_clipped: float | None = None, w_odd: float | None = None) -> float:
    """Combine the features into one quality number in [0, 1] (higher = more trustworthy text layer).
    The weights default to the module constants; router_config.json overrides them."""
    if not feats.get("n_tokens"):
        return 0.0
    wc = W_CLIPPED if w_clipped is None else w_clipped
    wo = W_ODD if w_odd is None else w_odd
    s = feats["dict_ratio"] - wc * feats["clipped_ratio"] - wo * feats["odd_char_ratio"]
    agree = feats.get("engine_agreement")
    if agree is not None:
        s *= 0.5 + 0.5 * agree          # two engines that disagree: one of them reads damaged data
    s *= min(1.0, feats["n_tokens"] / MIN_TOKENS_FULL_CONFIDENCE)
    return round(max(0.0, min(1.0, s)), 4)


def quality(text: str | None, other_text: str | None = None, **weights) -> tuple[float, dict]:
    feats = features(text, other_text)
    return score(feats, **weights), feats
