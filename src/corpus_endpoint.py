"""T4: stage S4 — did anything from these domains survive into a released
corpus subset for the target language?

Uses the HF dataset-viewer API (datasets-server.huggingface.co):
  /splits  -> which per-language configs exist at all (itself a finding)
  /filter  -> does any row in the language's subset have a URL on an
              inventory domain?

Corpora: HuggingFaceFW/fineweb-2 (configs like cho_Latn),
cis-lmu/GlotCC-V1 (configs like cho-Latn).

Writes results/corpus_endpoint.json.
"""

import io
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit, quote

import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://datasets-server.huggingface.co"
UA = ("crawlgap-research/0.1 (academic study of web-crawl coverage; "
      "contact: sharvingoyal09@gmail.com)")
DELAY_S = 1.0

# script per iso for config-name construction (Latn unless noted)
SCRIPTS = {"chr": ["Cher", "Latn"], "crk": ["Cans", "Latn"],
           "ciw": ["Latn"], "oji": ["Latn"]}


def get(url):
    time.sleep(DELAY_S)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    return r.status_code, (r.json() if r.status_code == 200 else r.text[:200])


t0 = time.time()
inv = json.load(io.open(ROOT / "results/inventory.json", encoding="utf-8"))
langs = {}
for c in inv["candidates"]:
    langs.setdefault(c["iso"], set()).add(urlsplit(c["url"]).netloc.lower())

CORPORA = {
    "fineweb-2": {"ds": "HuggingFaceFW/fineweb-2", "sep": "_",
                  "url_col": "url"},
    "glotcc-v1": {"ds": "cis-lmu/GlotCC-V1", "sep": "-", "url_col": "url"},
}

configs = {}
for name, spec in CORPORA.items():
    st, js = get(f"{API}/splits?dataset={quote(spec['ds'], safe='')}")
    if st != 200:
        configs[name] = None
        print(f"splits {name}: HTTP {st}")
        continue
    configs[name] = sorted({s["config"] for s in js["splits"]})
    print(f"{name}: {len(configs[name])} configs")

out = {}
for iso, domains in sorted(langs.items()):
    rec = {"domains_checked": sorted(domains), "corpora": {}}
    for name, spec in CORPORA.items():
        if configs[name] is None:
            rec["corpora"][name] = {"error": "splits_unavailable"}
            continue
        scripts = SCRIPTS.get(iso, ["Latn"])
        found_cfgs = [f"{iso}{spec['sep']}{s}" for s in scripts
                      if f"{iso}{spec['sep']}{s}" in configs[name]]
        crec = {"subset_exists": bool(found_cfgs), "configs": found_cfgs,
                "domain_hits": {}}
        for cfg in found_cfgs:
            for dom in sorted(domains):
                where = quote(f'"url" LIKE \'%{dom}%\'', safe="")
                st, js = get(
                    f"{API}/filter?dataset={quote(spec['ds'], safe='')}"
                    f"&config={cfg}&split=train&where={where}&limit=3")
                if st == 200:
                    n = js.get("num_rows_total", 0)
                    if n:
                        crec["domain_hits"][f"{cfg}:{dom}"] = n
                else:
                    crec["domain_hits"][f"{cfg}:{dom}"] = f"HTTP {st}"
        rec["corpora"][name] = crec
    out[iso] = rec
    print(iso, {k: v.get("subset_exists") for k, v in rec["corpora"].items()},
          {k: v for k, v in
           ((n, c.get("domain_hits")) for n, c in rec["corpora"].items()) if v})

io.open(ROOT / "results/corpus_endpoint.json", "w", encoding="utf-8").write(
    json.dumps({"config": {"script": "src/corpus_endpoint.py",
                           "corpora": {k: v["ds"] for k, v in CORPORA.items()},
                           "git_hash": subprocess.run(
                               ["git", "rev-parse", "--short", "HEAD"],
                               cwd=ROOT, capture_output=True,
                               text=True).stdout.strip(),
                           "run_unix": int(time.time())},
                "runtime_s": round(time.time() - t0, 1),
                "by_iso": out}, indent=1))
print(f"done {round(time.time()-t0,1)}s")
