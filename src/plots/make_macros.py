"""T5: emit paper/tables/macros.tex — every number the prose cites.

Reads results/*.json only. No hand-typed numbers may appear in main.tex.
"""

import io
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "results"


def load(name):
    p = R / f"{name}.json"
    return json.load(io.open(p, encoding="utf-8")) if p.exists() else None


inv = load("inventory")
deep = load("inventory_deep")
cov = load("cdx_coverage")
robots = load("robots")
endpoint = load("corpus_endpoint")
routing = load("lid_routing")
filters = load("filters")
funnel = load("funnel")

m = {}
langs = sorted({c["iso"] for c in inv["candidates"]})
fams = sorted({c["family"] for c in inv["candidates"]})
m["NLangs"] = len(langs)
m["NFams"] = len(fams)
m["NUrls"] = inv["n_candidates"]
m["NLive"] = inv["n_live"]
m["NDomains"] = len({urlsplit(c["url"]).netloc.lower()
                     for c in inv["candidates"]})
nolabel = sorted({c["iso"] for c in inv["candidates"]
                  if not c["lid_label_exists"]})
m["NLangsNoLabel"] = len(nolabel)
m["LangsNoLabel"] = ", ".join(nolabel)
m["NJsApp"] = sum(1 for c in inv["candidates"] if c.get("js_app_suspect"))

if deep:
    m["NDeepPairs"] = len(deep["best_pages"])
    m["NDeepWithText"] = sum(1 for b in deep["best_pages"]
                             if b["target_lines"] > 0)
    m["NDeepLangsWithText"] = len({b["iso"] for b in deep["best_pages"]
                                   if b["target_lines"] > 0})

if endpoint:
    by = endpoint["by_iso"]
    have = [i for i in langs if any(
        c.get("subset_exists") for c in by.get(i, {}).get("corpora",
                                                          {}).values())]
    m["NLangsWithSubset"] = len(have)
    sizes = []
    for i in have:
        for c in by[i]["corpora"].values():
            for cfg, n in (c.get("rows_scanned") or {}).items():
                if isinstance(n, int):
                    sizes.append((f"{cfg}", n))
    if sizes:
        m["SubsetMinDocs"] = min(n for _, n in sizes)
        m["SubsetMaxDocs"] = max(n for _, n in sizes)
        m["SubsetTotalDocs"] = sum(n for _, n in sizes)
    hits = sum(1 for i in langs for c in by.get(i, {}).get("corpora",
                                                           {}).values()
               for v in (c.get("domain_hits") or {}).values()
               if isinstance(v, int) and v > 0)
    m["NDomainHits"] = hits

if cov:
    urls = cov["url_captures"]
    m["NCrawls"] = len(cov["config"]["crawls"])
    m["NUrlsChecked"] = len(urls)
    m["NUrlsNeverCrawled"] = sum(
        1 for pc in urls.values() if not any(v["n"] for v in pc.values()))
    m["NUrlsNeverDef"] = sum(
        1 for pc in urls.values() if all(v["n"] == 0 for v in pc.values()))
    m["NUrlsCapturedNoOk"] = sum(
        1 for pc in urls.values()
        if any(v["n"] for v in pc.values())
        and not any(v.get("latest_200") for v in pc.values()))
    m["NUrlsDeepNew"] = m["NUrlsChecked"] - m["NUrls"]
    # captures found ONLY outside the six originally pinned crawls
    ORIG6 = {"CC-MAIN-2026-30", "CC-MAIN-2026-25", "CC-MAIN-2026-21",
             "CC-MAIN-2026-17", "CC-MAIN-2024-51", "CC-MAIN-2023-50"}
    m["NUrlsOkOnlyDeepCrawls"] = sum(
        1 for pc in urls.values()
        if any(v.get("latest_200") for v in pc.values())
        and not any(v.get("latest_200") for c, v in pc.items()
                    if c in ORIG6))
    m["NUrlsWithCapture"] = sum(
        1 for pc in urls.values()
        if any(v.get("latest_200") for v in pc.values()))
if robots:
    rr = robots["robots"]
    m["NHosts"] = len(rr)
    m["NHostsCcbotBlocked"] = sum(1 for r in rr.values()
                                  if r.get("ccbot_blocked_all"))
if routing:
    cnt = Counter(r["s2_status"] for r in routing["records"])
    m["NSTwoPass"] = cnt.get("pass", 0)
    m["NSTwoRouted"] = cnt.get("routed_elsewhere", 0)
    m["NSTwoLabelMissing"] = cnt.get("label_missing", 0)
    m["NSTwoRoutedEng"] = sum(
        1 for r in routing["records"]
        if r.get("s2_status") == "routed_elsewhere"
        and r.get("doc_lid_top3")
        and r["doc_lid_top3"][0][0] == "eng_Latn")
if filters:
    cnt = Counter(r["s3_status"] for r in filters["records"])
    m["NSThreeKept"] = cnt.get("kept", 0)
    m["NSThreeKilled"] = sum(v for k, v in cnt.items()
                             if k.startswith("killed"))
if funnel:
    ca = funnel["content_attribution"]
    m["NContentPages"] = sum(ca.values())
    m["NContentSFourPresent"] = ca.get("S4:present", 0)
    ia = funnel["institutional_attribution"]
    m["NInstPages"] = sum(ia.values())
    m["NInstSFourPresent"] = ia.get("S4:present", 0)
    m["NInstNeverCrawled"] = ia.get("S1:never_crawled", 0)

pdfs = load("pdf_links")
if pdfs:
    m["NPdfLinks"] = pdfs["total_pdf_links"]
    m["NPdfDomains"] = pdfs["n_domains_with_pdfs"]
    m["NLiveDomains"] = len(pdfs["pdf_links_per_domain"])

breadth = load("corpus_breadth")
if breadth:
    by = breadth["by_iso"]
    m["NMadladLangs"] = sum(
        1 for r in by.values()
        if isinstance(r.get("MADLAD-400"), list) and r["MADLAD-400"])
    m["NMadladAbsent"] = len(by) - m["NMadladLangs"]

dest = ROOT / "paper/tables/macros.tex"
dest.parent.mkdir(parents=True, exist_ok=True)
lines = [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in sorted(m.items())]
io.open(dest, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"{len(m)} macros -> {dest}")
for k, v in sorted(m.items()):
    print(f"  \\{k} = {v}")
