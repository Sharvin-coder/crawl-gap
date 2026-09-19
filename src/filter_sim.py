"""T3: stage S3 — would a FineWeb-2-style quality cascade keep the captured
page text?

Re-implementation of the standard public filter cascade used by
FineWeb-2/datatrove-style pipelines (Gopher quality + repetition signals,
C4 terminal-punctuation, and an LID-probability threshold), applied to the
text extracted from each URL's Common Crawl capture (from T2's cache).

Filters (first to fire wins; order pinned here):
  lid_prob        doc-level GlotLID top-1 prob < 0.65 for ANY label
                  (proxy for the pipeline's language-score gate)
  gopher_short    < 50 words
  gopher_alpha    < 80% of words contain an alphabetic character
  dup_line_frac   > 30% duplicate lines
  top_2gram       top character 2-gram > 20% of characters
  bullet_ratio    > 90% of lines start with a bullet/dash
  c4_punct        < 3 lines ending in terminal punctuation

Writes results/filters.json.
"""

import io
import json
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from warc_lid import fetch_record  # noqa: E402  (reuses warc cache)
from common import extract_text, lid  # noqa: E402

t0 = time.time()
cov = json.load(io.open(ROOT / "results/cdx_coverage.json", encoding="utf-8"))
routing = json.load(io.open(ROOT / "results/lid_routing.json",
                            encoding="utf-8"))["records"]


def first_filter(lines):
    text = "\n".join(lines)
    words = re.findall(r"\S+", text)
    doc_top = lid(text)[0]
    if doc_top[1] < 0.65:
        return "lid_prob", doc_top
    if len(words) < 50:
        return "gopher_short", doc_top
    alpha = sum(1 for w in words if re.search(r"[^\W\d_]", w))
    if alpha / len(words) < 0.8:
        return "gopher_alpha", doc_top
    if len(lines) >= 2:
        dup = 1 - len(set(lines)) / len(lines)
        if dup > 0.3:
            return "dup_line_frac", doc_top
    chars = re.sub(r"\s", "", text)
    if len(chars) >= 20:
        grams = Counter(chars[i:i + 2] for i in range(len(chars) - 1))
        if grams.most_common(1)[0][1] * 2 / len(chars) > 0.2:
            return "top_2gram", doc_top
    bullets = sum(1 for l in lines if re.match(r"^[-*•●·]", l))
    if lines and bullets / len(lines) > 0.9:
        return "bullet_ratio", doc_top
    punct_lines = sum(1 for l in lines if re.search(r'[.!?"”]\s*$', l))
    if punct_lines < 3:
        return "c4_punct", doc_top
    return None, doc_top


out = []
for r in routing:
    rec = {"url": r["url"], "iso": r["iso"], "s2_status": r["s2_status"]}
    if "crawl" not in r:      # nothing captured -> S3 not applicable
        rec["s3_status"] = "not_applicable"
        out.append(rec)
        continue
    cap = None
    for crawl in cov["config"]["crawls"]:
        lc = cov["url_captures"][r["url"]].get(crawl, {}).get("latest_200")
        if lc:
            cap = lc
            break
    lines = extract_text(fetch_record(cap))
    if not lines:
        rec["s3_status"] = "empty_payload_text"
        out.append(rec)
        continue
    fired, doc_top = first_filter(lines)
    rec.update(filter_fired=fired, doc_top1=doc_top,
               s3_status="killed:" + fired if fired else "kept")
    out.append(rec)
    print(f"{r['iso']:4} {rec['s3_status']:22} {r['url'][:60]}")

io.open(ROOT / "results/filters.json", "w", encoding="utf-8").write(
    json.dumps({"config": {"script": "src/filter_sim.py",
                           "order": ["lid_prob", "gopher_short",
                                     "gopher_alpha", "dup_line_frac",
                                     "top_2gram", "bullet_ratio", "c4_punct"],
                           "lid_prob_thresh": 0.65,
                           "git_hash": subprocess.run(
                               ["git", "rev-parse", "--short", "HEAD"],
                               cwd=ROOT, capture_output=True,
                               text=True).stdout.strip(),
                           "run_unix": int(time.time())},
                "runtime_s": round(time.time() - t0, 1),
                "records": out}, indent=1, ensure_ascii=False))
print(Counter(r["s3_status"] for r in out))
