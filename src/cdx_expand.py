"""Camera-ready: expand S1 crawl coverage (reviewer R6G1).

A static page crawled once in an older crawl would still be in FineWeb-2,
so 6 pinned crawls under-detect capture. This pass extends the check to
every Common Crawl release from 2023-2025, the two newest 2026 crawls,
and one crawl per year back to 2013 (spanning every crawl year FineWeb-2
draws on). Only URLs that so far lack any successful (HTTP-200) capture
are re-queried; URLs already captured need no further evidence.

Merges into results/cdx_coverage.json (idempotent via the shared cache).
"""

import hashlib
import io
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/cache/cdx"
UA = ("crawlgap-research/0.1 (academic study of web-crawl coverage; "
      "contact: sharvingoyal09@gmail.com)")
DELAY_S = 1.2
INDEX = "https://index.commoncrawl.org"
FL = "timestamp,status,mime,digest,length,filename,offset"

last_req = [0.0]


def get(url):
    key = hashlib.sha1(url.encode()).hexdigest()[:20]
    p = CACHE / f"{key}.json"
    if p.exists():
        d = json.load(io.open(p, encoding="utf-8"))
        if d["status"] in (200, 404):
            return d["status"], d["text"]
        p.unlink()
    for attempt in range(4):
        wait = DELAY_S - (time.time() - last_req[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            last_req[0] = time.time()
            if r.status_code in (502, 503, 504, 429):
                d = {"status": r.status_code, "text": ""}
                time.sleep(5 * (attempt + 1))
                continue
            d = {"status": r.status_code, "text": r.text}
            break
        except requests.RequestException as e:
            last_req[0] = time.time()
            d = {"status": None, "text": f"ERROR {type(e).__name__}"}
            time.sleep(5 * (attempt + 1))
    if d["status"] in (200, 404):
        io.open(p, "w", encoding="utf-8").write(json.dumps(d))
    return d["status"], d["text"]


def cdx_lines(status, text):
    if status != 200 or not text.strip():
        return []
    out = []
    for ln in text.strip().splitlines():
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            pass
    return out


t0 = time.time()
cov = json.load(io.open(ROOT / "results/cdx_coverage.json", encoding="utf-8"))
existing = set(cov["config"]["crawls"])

st, txt = get(f"{INDEX}/collinfo.json")
assert st == 200, f"collinfo failed: {st}"
all_crawls = [c["id"] for c in json.loads(txt)]

expansion = []
for c in all_crawls:
    year = c.split("-")[2][:4] if c.count("-") >= 2 else ""
    if year in ("2023", "2024", "2025"):
        expansion.append(c)
for c in all_crawls[:2]:          # two newest (2026-39, 2026-34)
    expansion.append(c)
for y in range(2013, 2023):       # one per year 2013-2022 (first listed)
    for c in all_crawls:
        if c.startswith(f"CC-MAIN-{y}"):
            expansion.append(c)
            break
new_crawls = sorted({c for c in expansion} - existing, reverse=True)
merged = sorted(existing | set(new_crawls), reverse=True)
print(f"{len(new_crawls)} new crawls: {new_crawls}")

targets = [u for u, pc in cov["url_captures"].items()
           if not any(v.get("latest_200") for v in pc.values())]
print(f"{len(targets)} URLs without a 200 capture to re-query")

n_new_captures = 0
for u in targets:
    for crawl in new_crawls:
        st, txt = get(f"{INDEX}/{crawl}-index?url={quote(u, safe='')}"
                      f"&output=json&limit=20&fl={FL}")
        rows = cdx_lines(st, txt)
        entry = {
            "n": len(rows) if st in (200, 404) else None,
            "statuses": sorted({r.get("status") for r in rows}) if rows
            else [],
            "latest_200": next(
                (r for r in sorted(rows, key=lambda r: r["timestamp"],
                                   reverse=True)
                 if r.get("status") == "200"), None),
        }
        cov["url_captures"][u][crawl] = entry
        if entry["latest_200"]:
            n_new_captures += 1
    hit = any(v.get("latest_200")
              for v in cov["url_captures"][u].values())
    print(("FOUND " if hit else "still-none ") + u[:70])

cov["config"]["crawls"] = merged
cov["config"]["expansion"] = {
    "script": "src/cdx_expand.py",
    "rule": ("all 2023-2025 crawls + two newest 2026 + one per year "
             "2013-2022; re-queried only URLs lacking a 200 capture"),
    "git_hash": subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
        capture_output=True, text=True).stdout.strip(),
    "run_unix": int(time.time()),
    "runtime_s": round(time.time() - t0, 1),
}
io.open(ROOT / "results/cdx_coverage.json", "w", encoding="utf-8").write(
    json.dumps(cov, indent=1))

urls = cov["url_captures"]
n200 = sum(1 for pc in urls.values()
           if any(v.get("latest_200") for v in pc.values()))
never = sum(1 for pc in urls.values()
            if all(v.get("n") == 0 for v in pc.values()))
print(f"\nAfter expansion over {len(merged)} crawls: {len(urls)} URLs, "
      f"{n200} with a 200 capture, {never} definitively never captured; "
      f"{round(time.time()-t0,1)}s")
