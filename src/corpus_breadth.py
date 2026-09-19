"""Camera-ready E3 (reviewer kqzB): do the 16 inventory languages have
per-language subsets in other broad-coverage corpora?

Checks config/subset existence via the HF dataset-viewer /splits API for
mC4, OSCAR-2301, MADLAD-400, and CulturaX, matching each language's
ISO 639-3 code plus its ISO 639-1 equivalent or macrolanguage code where
one exists. Existence-only (no downloads). Writes
results/corpus_breadth.json.
"""

import io
import json
import subprocess
import time
from urllib.parse import quote
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://datasets-server.huggingface.co"
UA = ("crawlgap-research/0.1 (academic study of web-crawl coverage; "
      "contact: sharvingoyal09@gmail.com)")

# iso639-3 -> additional codes that corpora might use for the language
ALT = {"nav": ["nv"], "crk": ["cr"], "ciw": ["oj", "ojb"],
       "chr": [], "cho": [], "cic": [], "mus": [], "lkt": [], "moh": [],
       "arp": [], "osa": [], "bla": [], "tli": [], "esu": [], "pot": [],
       "mez": []}

DATASETS = {
    "mC4": "legacy-datasets/mc4",
    "OSCAR-2301": "oscar-corpus/OSCAR-2301",
    "MADLAD-400": "allenai/MADLAD-400",
    "CulturaX": "uonlp/CulturaX",
}

t0 = time.time()
# The dataset-viewer /splits API is unavailable for these four datasets
# (gated or disabled). Language coverage is read from ungated
# authoritative sources instead: the mC4 dataset card's YAML `language:`
# list, the HF file trees of MADLAD-400 and CulturaX (per-language
# directories), and the OSCAR project's public documentation table.
import re


def _get(url):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=90)
    time.sleep(1.0)
    return r


configs = {}

r = _get("https://huggingface.co/datasets/legacy-datasets/mc4/raw/main/"
         "README.md")
langs = set()
in_fm = in_lang = False
for ln in r.text.splitlines():
    s = ln.strip()
    if s == "---":
        if in_fm:
            break
        in_fm = True
        continue
    if in_fm and s.startswith("language:"):
        in_lang = True
        continue
    if in_lang:
        if s.startswith("- "):
            langs.add(s[2:].strip().strip("'\""))
        elif s and not s.startswith("-"):
            in_lang = False
configs["mC4"] = sorted(langs)

r = _get("https://huggingface.co/api/datasets/allenai/MADLAD-400/tree/"
         "main/data")
configs["MADLAD-400"] = sorted(
    e["path"].split("/", 1)[1] for e in r.json()
    if e["type"] == "directory")

r = _get("https://huggingface.co/api/datasets/uonlp/CulturaX/tree/main")
configs["CulturaX"] = sorted(
    e["path"] for e in r.json()
    if e["type"] == "directory" and not e["path"].startswith("."))

r = _get("https://oscar-project.github.io/documentation/versions/"
         "oscar-2301/")
rows = re.findall(r"<tr>\s*<td[^>]*>\d+</td>\s*<td[^>]*>([a-zA-Z-]{2,12})"
                  r"</td>", r.text)
configs["OSCAR-2301"] = sorted(set(rows))

for name in DATASETS:
    print(f"{name}: {len(configs[name])} language codes")

out = {}
for iso, alts in sorted(ALT.items()):
    codes = [iso] + alts
    row = {}
    for name in DATASETS:
        cfgs = configs[name]
        if cfgs is None:
            row[name] = "api_unavailable"
            continue
        hits = [c for c in cfgs
                if c in codes or any(c.startswith(k + "_") or
                                     c.startswith(k + "-") for k in codes)]
        row[name] = hits
    out[iso] = row
    print(iso, row)

res = {"config": {"script": "src/corpus_breadth.py",
                  "datasets": DATASETS, "alt_codes": ALT,
                  "git_hash": subprocess.run(
                      ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                      capture_output=True, text=True).stdout.strip(),
                  "run_unix": int(time.time())},
       "runtime_s": round(time.time() - t0, 1),
       "n_configs": {k: (len(v) if v else None)
                     for k, v in configs.items()},
       "by_iso": out}
io.open(ROOT / "results/corpus_breadth.json", "w", encoding="utf-8").write(
    json.dumps(res, indent=1))
langs_with_any = [i for i, r in out.items()
                  if any(isinstance(v, list) and v for v in r.values())]
print(f"\nlanguages with any subset in the four corpora: {langs_with_any}")
