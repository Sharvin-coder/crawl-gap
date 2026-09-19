"""T1: Common Crawl coverage (stage S1) for every inventory candidate.

Per pinned crawl snapshot and per candidate URL:
  - exact-URL captures (status, mime, digest, and WARC filename/offset/length
    so T2 can retrieve the payload without re-querying)
  - host-level presence (any capture on the host at all, limit=1 probe)
Plus per-host live robots.txt CCBot policy (S1 mechanism attribution).

Etiquette: sequential, >=1.2 s between index queries, cache every response,
retry 503/504 with backoff. Writes results/cdx_config.json,
results/cdx_coverage.json, results/robots.json.
"""

import hashlib
import io
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit, quote

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/cache/cdx"
CACHE.mkdir(parents=True, exist_ok=True)
UA = ("crawlgap-research/0.1 (academic study of web-crawl coverage; "
      "contact: sharvingoyal09@gmail.com)")
DELAY_S = 1.2
INDEX = "https://index.commoncrawl.org"

last_req = [0.0]


def get(url, is_index=True):
    """Cached, throttled GET with backoff. Returns (status, text).

    Only 200 and 404 are cached: pywb's CDX API answers 404 for "no
    captures", which is a valid negative; transient errors must be
    retried on the next run, never persisted.
    """
    key = hashlib.sha1(url.encode()).hexdigest()[:20]
    p = CACHE / f"{key}.json"
    if p.exists():
        d = json.load(io.open(p, encoding="utf-8"))
        if d["status"] in (200, 404):
            return d["status"], d["text"]
        p.unlink()  # purge previously cached failure
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


def query_ok(status):
    return status in (200, 404)


t0 = time.time()

# -- pin crawl list ----------------------------------------------------------
st, txt = get(f"{INDEX}/collinfo.json")
assert st == 200, f"collinfo failed: {st}"
crawls_all = [c["id"] for c in json.loads(txt)]  # newest first
recent = crawls_all[:4]
historical = [next(c for c in crawls_all if c.startswith(f"CC-MAIN-{y}"))
              for y in (2024, 2023) if any(
                  c.startswith(f"CC-MAIN-{y}") for c in crawls_all)]
CRAWLS = recent + historical
io.open(ROOT / "results/cdx_config.json", "w", encoding="utf-8").write(
    json.dumps({"crawls": CRAWLS, "picked_from": len(crawls_all),
                "rule": "4 most recent + first-listed of 2024 and 2023",
                "pinned_unix": int(time.time())}, indent=1))
print("crawls:", CRAWLS)

# -- candidates --------------------------------------------------------------
inv = json.load(io.open(ROOT / "results/inventory.json", encoding="utf-8"))
cands = list(inv["candidates"])
deep_p = ROOT / "results/inventory_deep.json"
if deep_p.exists():
    for d in json.load(io.open(deep_p, encoding="utf-8"))["best_pages"]:
        cands.append({"url": d["url"], "iso": d["iso"], "lang": d["lang"]})
hosts = sorted({urlsplit(c["url"]).netloc.lower() for c in cands})

# -- host presence -----------------------------------------------------------
host_presence = {h: {} for h in hosts}
for h in hosts:
    for crawl in CRAWLS:
        st, txt = get(f"{INDEX}/{crawl}-index?url={quote(h)}"
                      f"&matchType=host&limit=1&output=json")
        host_presence[h][crawl] = bool(cdx_lines(st, txt)) \
            if query_ok(st) else None  # None = index query itself failed
    print("host", h, sum(1 for v in host_presence[h].values() if v), "/",
          len(CRAWLS))

# -- exact-URL captures ------------------------------------------------------
FL = "timestamp,status,mime,digest,length,filename,offset"
url_caps = {}
for c in cands:
    u = c["url"]
    if u in url_caps:
        continue
    per_crawl = {}
    for crawl in CRAWLS:
        st, txt = get(f"{INDEX}/{crawl}-index?url={quote(u, safe='')}"
                      f"&output=json&limit=20&fl={FL}")
        rows = cdx_lines(st, txt)
        per_crawl[crawl] = {
            "n": len(rows) if query_ok(st) else None,
            "statuses": sorted({r.get("status") for r in rows}) if rows else [],
            "latest_200": next(
                (r for r in sorted(rows, key=lambda r: r["timestamp"],
                                   reverse=True)
                 if r.get("status") == "200"), None),
        }
    url_caps[u] = per_crawl
    n_crawls_hit = sum(1 for v in per_crawl.values() if v["n"])
    print("url ", n_crawls_hit, "/", len(CRAWLS), u[:70])

# -- robots.txt CCBot policy -------------------------------------------------
robots = {}
for h in hosts:
    st, txt = get(f"https://{h}/robots.txt", is_index=False)
    rec = {"status": st, "has_robots": st == 200}
    if st == 200 and len(txt) < 200_000:
        blocks, cur_agents, rules = [], [], []
        for ln in txt.splitlines():
            ln = ln.split("#")[0].strip()
            if not ln:
                continue
            k, _, v = ln.partition(":")
            k, v = k.strip().lower(), v.strip()
            if k == "user-agent":
                if rules:
                    blocks.append((cur_agents, rules))
                    cur_agents, rules = [], []
                cur_agents.append(v.lower())
            elif k in ("allow", "disallow"):
                rules.append((k, v))
        if rules:
            blocks.append((cur_agents, rules))

        def blocked_all(agent):
            for agents, rules in blocks:
                if agent in agents or "*" in agents:
                    if any(k == "disallow" and v == "/" for k, v in rules):
                        return True
            return False

        rec["ccbot_named"] = any("ccbot" in a for ags, _ in blocks
                                 for a in ags)
        rec["ccbot_blocked_all"] = blocked_all("ccbot")
        rec["star_blocked_all"] = blocked_all("*")
    robots[h] = rec
    print("robots", h, rec.get("ccbot_blocked_all"), rec.get("star_blocked_all"))

git_hash = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
io.open(ROOT / "results/cdx_coverage.json", "w", encoding="utf-8").write(
    json.dumps({"config": {"script": "src/cdx_coverage.py", "crawls": CRAWLS,
                           "fl": FL, "git_hash": git_hash,
                           "run_unix": int(time.time())},
                "runtime_s": round(time.time() - t0, 1),
                "host_presence": host_presence,
                "url_captures": url_caps}, indent=1))
io.open(ROOT / "results/robots.json", "w", encoding="utf-8").write(
    json.dumps({"config": {"script": "src/cdx_coverage.py",
                           "git_hash": git_hash},
                "robots": robots}, indent=1))

n_urls = len(url_caps)
n_never = sum(1 for u, pc in url_caps.items()
              if not any(v["n"] for v in pc.values()))
print(f"\n{n_urls} URLs; {n_never} with zero captures across {len(CRAWLS)} "
      f"crawls; {round(time.time()-t0,1)}s")
