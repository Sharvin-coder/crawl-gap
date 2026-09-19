"""Camera-ready E2 (reviewer 6uHY): how much content on the inventory
sites lives in PDFs?

Counts distinct PDF links in the cached page fetches (homepages plus the
deepened content pages already in data/cache/live/), per live inventory
domain. No new fetches. Writes results/pdf_links.json.
"""

import io
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/cache/live"

HREF = re.compile(r"""href=["']([^"']+?\.pdf(?:[?#][^"']*)?)["']""", re.I)

t0 = time.time()
inv = json.load(io.open(ROOT / "results/inventory.json", encoding="utf-8"))
live_domains = {urlsplit(c["url"]).netloc.lower()
                for c in inv["candidates"] if c["live"]}

# map cached bodies back to their fetched URL via the meta jsons
per_domain = {d: set() for d in live_domains}
n_pages = 0
for meta_p in CACHE.glob("*.json"):
    meta = json.load(io.open(meta_p, encoding="utf-8"))
    url = meta.get("final_url") or meta.get("url", "")
    dom = urlsplit(url).netloc.lower()
    if dom not in per_domain:
        continue
    body_p = meta_p.with_suffix(".html")
    if not body_p.exists():
        continue
    body = io.open(body_p, encoding="utf-8", errors="replace").read()
    if not body:
        continue
    n_pages += 1
    for href in HREF.findall(body):
        per_domain[dom].add(urljoin(url, href).split("#")[0])

counts = {d: len(v) for d, v in sorted(per_domain.items())}
res = {
    "config": {"script": "src/pdf_links.py",
               "source": "cached fetches in data/cache/live (no new "
                         "requests); distinct absolute .pdf hrefs per "
                         "live inventory domain",
               "n_cached_pages_scanned": n_pages,
               "git_hash": subprocess.run(
                   ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                   capture_output=True, text=True).stdout.strip(),
               "run_unix": int(time.time())},
    "runtime_s": round(time.time() - t0, 1),
    "pdf_links_per_domain": counts,
    "n_domains_with_pdfs": sum(1 for v in counts.values() if v),
    "total_pdf_links": sum(counts.values()),
}
io.open(ROOT / "results/pdf_links.json", "w", encoding="utf-8").write(
    json.dumps(res, indent=1))
for d, n in counts.items():
    if n:
        print(f"{n:4}  {d}")
print(f"\n{res['n_domains_with_pdfs']}/{len(counts)} live domains link "
      f"PDFs; {res['total_pdf_links']} distinct PDF links across "
      f"{n_pages} cached pages; {res['runtime_s']}s")
