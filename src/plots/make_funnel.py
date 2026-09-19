"""T5: aggregate the S0–S4 funnel and emit table + figure.

Reads results/{inventory,inventory_deep,cdx_coverage,robots,lid_routing,
filters,corpus_endpoint}.json. Writes results/funnel.json,
paper/tables/funnel.tex, figures/funnel.pdf.

Funnel population: the best content page per (iso, domain) from
inventory_deep (machine-verified target text where available), plus every
verified-live inventory URL for the institutional view.

First-failure attribution categories (ordered):
  S1:never_crawled   no CC capture of the URL in any pinned crawl
  S1:no_200          captured but never with HTTP 200
  S2:label_missing   language absent from GlotLID label space
  S2:routed_elsewhere captured text not recognized as target
  S3:killed          FineWeb-2-style cascade drops the page
  S4:absent          survives S1–S3 but domain absent from released subsets
  S4:present         domain has rows in a released per-language subset
"""

import io
import json
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "results"


def load(name):
    return json.load(io.open(R / f"{name}.json", encoding="utf-8"))


inv = load("inventory")
deep = load("inventory_deep")
cov = load("cdx_coverage")
robots = load("robots")["robots"]
routing = {r["url"]: r for r in load("lid_routing")["records"]}
filters = {r["url"]: r for r in load("filters")["records"]}
endpoint = load("corpus_endpoint")["by_iso"]

CATS = ["S1:never_crawled", "S1:no_200", "S2:label_missing",
        "S2:routed_elsewhere", "S3:killed", "S4:absent", "S4:present"]


def endpoint_present(iso, domain):
    rec = endpoint.get(iso)
    if not rec:
        return False
    for crec in rec["corpora"].values():
        for key, n in (crec.get("domain_hits") or {}).items():
            if isinstance(n, int) and n > 0 and key.split(":", 1)[1] == domain:
                return True
    return False


def s1_definitive(url):
    per_crawl = cov["url_captures"].get(url)
    return per_crawl is not None and all(v["n"] == 0
                                         for v in per_crawl.values())


def attribute(url, iso):
    per_crawl = cov["url_captures"].get(url)
    if per_crawl is None or not any(v["n"] for v in per_crawl.values()):
        return "S1:never_crawled"
    if not any(v.get("latest_200") for v in per_crawl.values()):
        return "S1:no_200"
    r = routing.get(url, {})
    st = r.get("s2_status", "")
    if st.startswith("warc_fetch_failed") or st == "empty_payload_text":
        return "S1:no_200"  # capture exists but record unusable
    if st == "label_missing":
        return "S2:label_missing"
    if st != "pass":
        return "S2:routed_elsewhere"
    f = filters.get(url, {})
    if f.get("s3_status", "").startswith("killed"):
        return "S3:killed"
    dom = urlsplit(url).netloc.lower()
    return "S4:present" if endpoint_present(iso, dom) else "S4:absent"


# -- content funnel (best page per iso×domain, target evidence required) -----
content_rows = []
for b in deep["best_pages"]:
    if b["target_lines"] == 0:
        continue
    cat = attribute(b["url"], b["iso"])
    content_rows.append({**{k: b[k] for k in
                            ("iso", "lang", "domain", "url",
                             "target_lines", "target_line_frac")},
                         "attribution": cat})

# -- institutional view (all live inventory URLs) ----------------------------
inst_rows = []
for c in inv["candidates"]:
    if not c["live"]:
        continue
    inst_rows.append({"iso": c["iso"], "url": c["url"],
                      "domain": urlsplit(c["url"]).netloc.lower(),
                      "js_app_suspect": c["js_app_suspect"],
                      "attribution": attribute(c["url"], c["iso"])})

by_lang = defaultdict(Counter)
for r in content_rows:
    by_lang[f"{r['lang']} ({r['iso']})"][r["attribution"]] += 1

host_stats = {
    "hosts": len(robots),
    "ccbot_blocked_all": sum(1 for r in robots.values()
                             if r.get("ccbot_blocked_all")),
    "star_blocked_all": sum(1 for r in robots.values()
                            if r.get("star_blocked_all")),
}

funnel = {
    "config": {"script": "src/plots/make_funnel.py",
               "git_hash": subprocess.run(
                   ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                   capture_output=True, text=True).stdout.strip(),
               "run_unix": int(time.time())},
    "categories": CATS,
    "content_rows": content_rows,
    "content_attribution": dict(Counter(r["attribution"]
                                        for r in content_rows)),
    "institutional_rows": inst_rows,
    "institutional_attribution": dict(Counter(r["attribution"]
                                              for r in inst_rows)),
    "s1_never_definitive": {
        "content": sum(1 for r in content_rows
                       if r["attribution"] == "S1:never_crawled"
                       and s1_definitive(r["url"])),
        "institutional": sum(1 for r in inst_rows
                             if r["attribution"] == "S1:never_crawled"
                             and s1_definitive(r["url"])),
    },
    "robots_summary": host_stats,
}
io.open(R / "funnel.json", "w", encoding="utf-8").write(
    json.dumps(funnel, indent=1, ensure_ascii=False))

# -- LaTeX table -------------------------------------------------------------
(ROOT / "paper/tables").mkdir(parents=True, exist_ok=True)
short = {"S1:never_crawled": "S1 never", "S1:no_200": "S1 no-200",
         "S2:label_missing": "S2 no-label", "S2:routed_elsewhere": "S2 miss",
         "S3:killed": "S3 killed", "S4:absent": "S4 absent",
         "S4:present": "S4 present"}
lines = [r"\resizebox{\columnwidth}{!}{%",
         r"\begin{tabular}{l" + "r" * len(CATS) + "}", r"\toprule",
         "Language & " + " & ".join(short[c] for c in CATS) + r" \\",
         r"\midrule"]
for lang in sorted(by_lang):
    cnt = by_lang[lang]
    lines.append(lang + " & " +
                 " & ".join(str(cnt.get(c, 0)) for c in CATS) + r" \\")
tot = Counter(r["attribution"] for r in content_rows)
lines += [r"\midrule", "Total & " +
          " & ".join(str(tot.get(c, 0)) for c in CATS) + r" \\",
          r"\bottomrule", r"\end{tabular}}"]
io.open(ROOT / "paper/tables/funnel.tex", "w", encoding="utf-8").write(
    "\n".join(lines) + "\n")

# -- figure (Okabe-Ito, colorblind-safe) -------------------------------------
OKABE = {"S1:never_crawled": "#E69F00", "S1:no_200": "#F0E442",
         "S2:label_missing": "#D55E00", "S2:routed_elsewhere": "#CC79A7",
         "S3:killed": "#56B4E9", "S4:absent": "#999999",
         "S4:present": "#009E73"}
langs = sorted(by_lang, reverse=True)
fig, ax = plt.subplots(figsize=(7, 0.5 * len(langs) + 2.0))
left = {l: 0 for l in langs}
for cat in CATS:
    vals = [by_lang[l].get(cat, 0) for l in langs]
    ax.barh(langs, vals, left=[left[l] for l in langs],
            color=OKABE[cat], label=short[cat], height=0.72)
    for l, v in zip(langs, vals):
        left[l] += v
from matplotlib.ticker import MaxNLocator
ax.xaxis.set_major_locator(MaxNLocator(integer=True))
ax.set_xlabel("content pages (best per site)", fontsize=12)
ax.tick_params(labelsize=12)
ax.legend(ncol=3, fontsize=11, loc="upper center",
          bbox_to_anchor=(0.5, -0.16), frameon=False,
          handlelength=1.2, columnspacing=1.1)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
(ROOT / "figures").mkdir(exist_ok=True)
fig.savefig(ROOT / "figures/funnel.pdf")
print(json.dumps(funnel["content_attribution"], indent=1))
print(json.dumps(funnel["institutional_attribution"], indent=1))
print("robots:", host_stats)
