"""T4 (corrected): stage S4 via direct parquet download + domain scan.

The dataset-viewer /filter endpoint 500s/422s on these datasets (see
FAILURES.md), so instead: for every per-language config that exists
(from results/corpus_endpoint.json), list its train-split parquet files via
the HF tree API, download them (these subsets are tiny; hard cap per config
below), and count rows whose URL falls on an inventory domain.

Rewrites results/corpus_endpoint.json in the same shape, with integer
domain_hits. Parquets cached in data/raw/ (not committed).
"""

import io
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit, quote

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
RAW.mkdir(parents=True, exist_ok=True)
UA = ("crawlgap-research/0.1 (academic study of web-crawl coverage; "
      "contact: sharvingoyal09@gmail.com)")
CAP_BYTES = 500 * 1024 * 1024  # per config

CORPORA = {
    "fineweb-2": {"ds": "HuggingFaceFW/fineweb-2", "url_col": "url",
                  "prefix": lambda cfg: f"data/{cfg}/train"},
    "glotcc-v1": {"ds": "cis-lmu/GlotCC-V1", "url_col": "warc-target-uri",
                  "prefix": lambda cfg: f"v1.0/{cfg}"},
}


def api(url):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    return r.status_code, (r.json() if r.status_code == 200 else r.text[:300])


def tree(ds, path):
    st, js = api(f"https://huggingface.co/api/datasets/{ds}"
                 f"/tree/main/{quote(path)}")
    if st != 200:
        return None
    return [f for f in js if f["path"].endswith(".parquet")]


def download(ds, fpath):
    dest = RAW / ds.replace("/", "__") / fpath.replace("/", "__")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        url = (f"https://huggingface.co/datasets/{ds}/resolve/main/"
               f"{quote(fpath)}")
        with requests.get(url, headers={"User-Agent": UA}, stream=True,
                          timeout=300) as r:
            r.raise_for_status()
            with io.open(dest, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
        time.sleep(0.5)
    return dest


t0 = time.time()
prev = json.load(io.open(ROOT / "results/corpus_endpoint.json",
                         encoding="utf-8"))
inv = json.load(io.open(ROOT / "results/inventory.json", encoding="utf-8"))
langs = {}
for c in inv["candidates"]:
    langs.setdefault(c["iso"], set()).add(urlsplit(c["url"]).netloc.lower())
deep_p = ROOT / "results/inventory_deep.json"
if deep_p.exists():
    for d in json.load(io.open(deep_p, encoding="utf-8"))["best_pages"]:
        langs.setdefault(d["iso"], set()).add(d["domain"])

out = {}
for iso, domains in sorted(langs.items()):
    rec = {"domains_checked": sorted(domains), "corpora": {}}
    for name, spec in CORPORA.items():
        prev_c = prev["by_iso"].get(iso, {}).get("corpora", {}).get(name, {})
        cfgs = prev_c.get("configs", [])
        crec = {"subset_exists": bool(cfgs), "configs": cfgs,
                "domain_hits": {}, "rows_scanned": {}}
        for cfg in cfgs:
            files = tree(spec["ds"], spec["prefix"](cfg))
            if files is None:
                crec["rows_scanned"][cfg] = "tree_api_failed"
                continue
            total = sum(f.get("size", 0) for f in files)
            if total > CAP_BYTES:
                crec["rows_scanned"][cfg] = f"skipped_too_big:{total}"
                continue
            n_rows = 0
            for f in files:
                try:
                    p = download(spec["ds"], f["path"])
                    df = pd.read_parquet(p, columns=[spec["url_col"]])
                except Exception as e:
                    crec["rows_scanned"][cfg] = f"error:{type(e).__name__}"
                    break
                n_rows += len(df)
                doms = df[spec["url_col"]].map(
                    lambda u: urlsplit(u).netloc.lower())
                for dom in domains:
                    n = int((doms == dom).sum())
                    if n:
                        k = f"{cfg}:{dom}"
                        crec["domain_hits"][k] = \
                            crec["domain_hits"].get(k, 0) + n
            else:
                crec["rows_scanned"][cfg] = n_rows
        rec["corpora"][name] = crec
    out[iso] = rec
    print(iso, {n: (c["configs"], c["domain_hits"], c["rows_scanned"])
                for n, c in rec["corpora"].items() if c["configs"]})

io.open(ROOT / "results/corpus_endpoint.json", "w", encoding="utf-8").write(
    json.dumps({"config": {"script": "src/corpus_endpoint_dl.py",
                           "method": "direct parquet scan (train split)",
                           "cap_bytes": CAP_BYTES,
                           "corpora": {k: v["ds"] for k, v in CORPORA.items()},
                           "git_hash": subprocess.run(
                               ["git", "rev-parse", "--short", "HEAD"],
                               cwd=ROOT, capture_output=True,
                               text=True).stdout.strip(),
                           "run_unix": int(time.time())},
                "runtime_s": round(time.time() - t0, 1),
                "by_iso": out}, indent=1))
print(f"done {round(time.time()-t0,1)}s")
