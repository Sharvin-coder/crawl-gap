"""T0c: deepen the inventory — find content-bearing pages.

Site homepages are institutionally English; the funnel needs pages that carry
server-visible target-language running text. For every live candidate, this
script extracts same-host internal links whose URL/anchor suggests language
content (lessons, stories, words, phrases, hymns, texts, dictionary browse),
fetches up to MAX_PER_SITE of them (cached, polite), scores target-language
evidence, and records the best page per (iso, domain).

Evidence (relaxed, pinned): a line counts as target if its top-1 GlotLID
label is in the language's accept set with p >= 0.3. Accept sets extend the
individual ISO with macrolanguage/closely-allied codes where the individual
code has no GlotLID label (documented in ACCEPT below).

Writes results/inventory_deep.json.
"""

import io
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from common import extract_text, labels_for_iso, model
from verify_inventory import fetch

ROOT = Path(__file__).resolve().parents[1]
MAX_PER_SITE = 4
LINE_P = 0.3

# macro/allied codes accepted as evidence where the individual ISO lacks a
# GlotLID label (ciw -> Ojibwe cluster; lkt -> Dakota; crk -> Cree cluster;
# esu -> Yupik cluster). Everything else: the individual code only.
ACCEPT = {"ciw": ["ciw", "oji", "ojb", "ojs", "ojw", "ojg", "otw"],
          "lkt": ["lkt", "dak"],
          "crk": ["crk", "cwd", "csw"],
          "esu": ["esu", "ess", "ems"]}

KEYWORDS = re.compile(
    r"lesson|stor(y|ies)|word|vocab|phrase|dictionar|browse|learn|language"
    r"|hymn|prayer|text|audio|glossary|grammar|translat", re.I)
HREF = re.compile(r"""<a[^>]+href=["']([^"'#]+)["'][^>]*>(.*?)</a>""",
                  re.S | re.I)


def accept_labels(iso):
    labs = set()
    for code in ACCEPT.get(iso, [iso]):
        labs.update(l.replace("__label__", "") for l in labels_for_iso(code))
    return labs


def line_evidence(lines, labs):
    if not lines or not labs:
        return 0, 0.0
    hits = 0
    for ln in lines:
        pred, prob = model.predict(ln.replace("\n", " ")[:2000], k=1)
        if pred and pred[0].replace("__label__", "") in labs \
                and float(prob[0]) >= LINE_P:
            hits += 1
    return hits, round(hits / len(lines), 3)


t0 = time.time()
inv = json.load(io.open(ROOT / "results/inventory.json", encoding="utf-8"))
best = {}
for c in inv["candidates"]:
    if not c["live"]:
        continue
    meta, body = fetch(c["url"])          # cache hit; no re-fetch
    host = urlsplit(c["url"]).netloc.lower()
    links = []
    for href, anchor in HREF.findall(body or ""):
        absu = urljoin(meta.get("final_url") or c["url"], href.strip())
        sp = urlsplit(absu)
        if sp.scheme not in ("http", "https") or sp.netloc.lower() != host:
            continue
        if KEYWORDS.search(absu) or KEYWORDS.search(re.sub(r"<[^>]+>", "",
                                                           anchor)[:120]):
            links.append(absu.split("#")[0])
    seen, picked = set(), []
    for u in links:
        if u not in seen and u != c["url"]:
            seen.add(u)
            picked.append(u)
        if len(picked) >= MAX_PER_SITE:
            break
    labs = accept_labels(c["iso"])
    key = (c["iso"], host)
    # score the original page too, so every (iso, domain) has a baseline
    cands = [c["url"]] + picked
    for u in cands:
        m, b = fetch(u)
        if not (m.get("status") and m["status"] < 400) or not b:
            continue
        lines = extract_text(b)
        hits, frac = line_evidence(lines, labs)
        cur = best.get(key)
        if cur is None or (hits, frac) > (cur["target_lines"],
                                          cur["target_line_frac"]):
            best[key] = {"iso": c["iso"], "lang": c["lang"], "domain": host,
                         "url": u, "parent": c["url"],
                         "n_lines": len(lines),
                         "target_lines": hits, "target_line_frac": frac,
                         "accept_labels": sorted(labs),
                         "found_via": ("inventory candidate" if u == c["url"]
                                       else f"auto-discovered link from {c['url']}")}
    b = best.get(key)
    if b:
        print(f"{c['iso']:4} {host:35} best={b['target_lines']:3} lines "
              f"({b['target_line_frac']}) {b['url'][:50]}")

res = {"config": {"script": "src/deepen_inventory.py",
                  "max_per_site": MAX_PER_SITE, "line_p": LINE_P,
                  "accept": ACCEPT,
                  "git_hash": subprocess.run(
                      ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                      capture_output=True, text=True).stdout.strip(),
                  "run_unix": int(time.time())},
       "runtime_s": round(time.time() - t0, 1),
       "best_pages": sorted(best.values(),
                            key=lambda r: (r["iso"], r["domain"]))}
io.open(ROOT / "results/inventory_deep.json", "w", encoding="utf-8").write(
    json.dumps(res, indent=1, ensure_ascii=False))
n_txt = sum(1 for r in best.values() if r["target_lines"] > 0)
print(f"\n{len(best)} (iso,domain) pairs; {n_txt} with target-language "
      f"evidence; {res['runtime_s']}s")
