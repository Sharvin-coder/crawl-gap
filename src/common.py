"""Shared helpers: GlotLID model, HTML text extraction, label utilities."""

import re
from html import unescape
from pathlib import Path

import os

import fasttext

ROOT = Path(__file__).resolve().parents[1]
GLOTLID = Path(os.environ.get("GLOTLID_MODEL",
                              "models/glotlid_v3_model.bin"))
UA = ("crawlgap-research/0.1 (academic study of web-crawl coverage; "
      "contact: sharvingoyal09@gmail.com)")

model = fasttext.load_model(str(GLOTLID))
# predict-only fasttext build: recover the full label set via one high-k call
_all, _ = model.predict("a", k=100000)
ALL_LABELS = set(_all)
assert len(ALL_LABELS) > 1500, f"label recovery failed: {len(ALL_LABELS)}"


def labels_for_iso(iso):
    pre = f"__label__{iso}_"
    return sorted(l for l in ALL_LABELS if l.startswith(pre))


TAG_STRIP = [
    (re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.S | re.I), " "),
    (re.compile(r"<!--.*?-->", re.S), " "),
    (re.compile(r"<[^>]+>"), "\n"),
]


def extract_text(html):
    t = html
    for rx, rep in TAG_STRIP:
        t = rx.sub(rep, t)
    t = unescape(t)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in t.splitlines()]
    return [ln for ln in lines if len(ln) >= 20]


def lid(text, k=3):
    labels, probs = model.predict(text.replace("\n", " ")[:4000], k=k)
    return [(l.replace("__label__", ""), round(float(p), 3))
            for l, p in zip(labels, probs)]
