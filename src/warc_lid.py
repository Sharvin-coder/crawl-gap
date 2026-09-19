"""T2: stage S2 — what does LID see in the actual Common Crawl capture?

For each candidate URL with at least one HTTP-200 capture (from
results/cdx_coverage.json), retrieve that single WARC record via an HTTP
range request, extract text from the captured HTML, and run GlotLID v3.

s2_pass definition (pinned): doc-level top-1 label is one of the language's
GlotLID labels, OR >=10% of text lines (>=20 chars) are labeled target with
p>=0.5. Languages with no GlotLID label at all cannot pass S2 by definition
(recorded as label_missing).

Writes results/lid_routing.json. Payloads cached in data/cache/warc/.
"""

import gzip
import hashlib
import io
import json
import subprocess
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/cache/warc"
CACHE.mkdir(parents=True, exist_ok=True)
UA = ("crawlgap-research/0.1 (academic study of web-crawl coverage; "
      "contact: sharvingoyal09@gmail.com)")
DATA = "https://data.commoncrawl.org"
LINE_FRAC_THRESH = 0.10
LINE_PROB_THRESH = 0.5

from common import extract_text, labels_for_iso, lid  # noqa: E402


def fetch_record(cap):
    key = hashlib.sha1(
        f"{cap['filename']}:{cap['offset']}".encode()).hexdigest()[:16]
    p = CACHE / f"{key}.bin"
    if not p.exists():
        off, ln = int(cap["offset"]), int(cap["length"])
        r = requests.get(f"{DATA}/{cap['filename']}",
                         headers={"User-Agent": UA,
                                  "Range": f"bytes={off}-{off+ln-1}"},
                         timeout=120)
        r.raise_for_status()
        p.write_bytes(r.content)
        time.sleep(1.0)
    raw = gzip.decompress(p.read_bytes())
    # WARC record: warc headers \r\n\r\n http headers \r\n\r\n payload
    parts = raw.split(b"\r\n\r\n", 2)
    payload = parts[2] if len(parts) == 3 else parts[-1]
    return payload.decode("utf-8", errors="replace")


def main():
    t0 = time.time()
    cov = json.load(io.open(ROOT / "results/cdx_coverage.json",
                            encoding="utf-8"))
    inv = json.load(io.open(ROOT / "results/inventory.json",
                            encoding="utf-8"))
    by_url = {}
    for c in inv["candidates"]:
        by_url.setdefault(c["url"], c)
    deep_p = ROOT / "results/inventory_deep.json"
    if deep_p.exists():
        for d in json.load(io.open(deep_p, encoding="utf-8"))["best_pages"]:
            by_url.setdefault(d["url"], {
                "url": d["url"], "iso": d["iso"], "lang": d["lang"],
                "lid_label_exists": bool(labels_for_iso(d["iso"]))})

    out = []
    for url, per_crawl in cov["url_captures"].items():
        c = by_url[url]
        cap = cap_crawl = None
        for crawl in cov["config"]["crawls"]:  # newest first
            lc = per_crawl.get(crawl, {}).get("latest_200")
            if lc:
                cap, cap_crawl = lc, crawl
                break
        rec = {"url": url, "iso": c["iso"], "lang": c["lang"],
               "lid_label_exists": c["lid_label_exists"]}
        if cap is None:
            rec["s2_status"] = "no_200_capture"
            out.append(rec)
            continue
        try:
            html = fetch_record(cap)
        except Exception as e:
            rec["s2_status"] = f"warc_fetch_failed:{type(e).__name__}"
            out.append(rec)
            continue
        lines = extract_text(html)
        chars = sum(len(l) for l in lines)
        rec.update(crawl=cap_crawl, cc_timestamp=cap["timestamp"],
                   cc_text_chars=chars, cc_n_lines=len(lines))
        if not lines:
            rec["s2_status"] = "empty_payload_text"
            out.append(rec)
            continue
        iso_labels = [l.replace("__label__", "")
                      for l in labels_for_iso(c["iso"])]
        rec["doc_lid_top3"] = lid(" ".join(lines))
        if iso_labels:
            per_line = [lid(ln, k=1)[0] for ln in lines]
            hits = sum(1 for lab, p in per_line
                       if lab in iso_labels and p >= LINE_PROB_THRESH)
            frac = hits / len(lines)
            rec["target_lines"] = hits
            rec["target_line_frac"] = round(frac, 3)
            top1 = rec["doc_lid_top3"][0][0]
            rec["s2_pass"] = top1 in iso_labels or frac >= LINE_FRAC_THRESH
            rec["s2_status"] = "pass" if rec["s2_pass"] else "routed_elsewhere"
        else:
            rec["s2_pass"] = False
            rec["s2_status"] = "label_missing"
        out.append(rec)
        print(f"{c['iso']:4} {rec['s2_status']:18} top1="
              f"{rec.get('doc_lid_top3', [('-', 0)])[0][0]:14} {url[:60]}")

    io.open(ROOT / "results/lid_routing.json", "w", encoding="utf-8").write(
        json.dumps({"config": {"script": "src/warc_lid.py",
                               "line_frac_thresh": LINE_FRAC_THRESH,
                               "line_prob_thresh": LINE_PROB_THRESH,
                               "git_hash": subprocess.run(
                                   ["git", "rev-parse", "--short", "HEAD"],
                                   cwd=ROOT, capture_output=True,
                                   text=True).stdout.strip(),
                               "run_unix": int(time.time())},
                    "runtime_s": round(time.time() - t0, 1),
                    "records": out}, indent=1, ensure_ascii=False))
    from collections import Counter
    print(Counter(r["s2_status"] for r in out))


if __name__ == "__main__":
    main()
