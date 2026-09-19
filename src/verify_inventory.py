"""T0b: verify inventory candidates.

For each candidate URL: polite fetch (cached), extract visible text, and
record (a) liveness, (b) whether GlotLID v3 even has a label for the
language, (c) GlotLID evidence that target-language text is present
(line-level and doc-level), (d) a JS-app heuristic (client-rendered pages
expose little text to any crawler).

Writes results/inventory.json. Page text stays in data/cache/ (uncommitted).
"""

import hashlib
import io
import json
import subprocess
import time
from pathlib import Path

import requests

from common import UA, extract_text, labels_for_iso, lid

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/cache/live"
CACHE.mkdir(parents=True, exist_ok=True)
DELAY_S = 1.5


def fetch(url):
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    meta_p, body_p = CACHE / f"{key}.json", CACHE / f"{key}.html"
    if meta_p.exists():
        meta = json.load(io.open(meta_p, encoding="utf-8"))
        body = io.open(body_p, encoding="utf-8", errors="replace").read() \
            if body_p.exists() else ""
        return meta, body
    meta = {"url": url, "fetched_unix": int(time.time())}
    body = ""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30,
                         allow_redirects=True)
        meta.update(status=r.status_code, final_url=r.url,
                    content_type=r.headers.get("content-type", ""))
        if "text" in meta["content_type"] or "html" in meta["content_type"]:
            body = r.text
    except requests.RequestException as e:
        meta.update(status=None, error=type(e).__name__)
    io.open(meta_p, "w", encoding="utf-8").write(json.dumps(meta))
    io.open(body_p, "w", encoding="utf-8", errors="replace").write(body)
    time.sleep(DELAY_S)
    return meta, body


def main():
    t0 = time.time()
    cands = json.load(io.open(ROOT / "data/inventory/candidates.json",
                              encoding="utf-8"))["candidates"]
    out = []
    for c in cands:
        meta, body = fetch(c["url"])
        lines = extract_text(body) if body else []
        text_chars = sum(len(l) for l in lines)
        iso_labels = [l.replace("__label__", "") for l in labels_for_iso(c["iso"])]
        rec = {**c,
               "live": bool(meta.get("status") and meta["status"] < 400),
               "status": meta.get("status"), "final_url": meta.get("final_url"),
               "text_chars": text_chars, "n_lines": len(lines),
               "js_app_suspect": bool(body) and text_chars < 500,
               "glotlid_labels_for_iso": iso_labels,
               "lid_label_exists": bool(iso_labels)}
        if lines:
            rec["doc_lid_top3"] = lid(" ".join(lines))
            if iso_labels:
                hits = 0
                per_line = [lid(ln, k=1)[0] for ln in lines]
                hits = sum(1 for (lab, p) in per_line
                           if lab in iso_labels and p >= 0.5)
                rec["target_lines"] = hits
                rec["target_line_frac"] = round(hits / len(lines), 3)
            else:
                rec["target_lines"] = None
                rec["target_line_frac"] = None
        out.append(rec)
        print(f"{c['iso']:4} {rec['status']} chars={text_chars:6} "
              f"lid_label={rec['lid_label_exists']} "
              f"tgt={rec.get('target_line_frac')} {c['url'][:60]}")

    res = {
        "config": {"script": "src/verify_inventory.py", "glotlid": "v3",
                   "ua": UA, "delay_s": DELAY_S,
                   "git_hash": subprocess.run(
                       ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                       capture_output=True, text=True).stdout.strip(),
                   "run_unix": int(time.time())},
        "runtime_s": round(time.time() - t0, 1),
        "n_candidates": len(out),
        "n_live": sum(1 for r in out if r["live"]),
        "n_lid_label_missing": sum(1 for r in out if not r["lid_label_exists"]),
        "candidates": out,
    }
    io.open(ROOT / "results/inventory.json", "w", encoding="utf-8").write(
        json.dumps(res, indent=1, ensure_ascii=False))
    print(f"\n{res['n_live']}/{len(out)} live; "
          f"{res['n_lid_label_missing']} lack any GlotLID label; "
          f"{res['runtime_s']}s -> results/inventory.json")


if __name__ == "__main__":
    main()
