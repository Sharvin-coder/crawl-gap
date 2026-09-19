# The Crawl Gap: Where Endangered-Language Web Content Is Lost Before It Reaches a Corpus

Code, inventory, and per-stage results for the paper, accepted at
**WaC-13** (13th Web-as-Corpus Workshop, EMNLP 2026, Budapest).

The paper traces a verified inventory of 45 web pages (40 curated plus 5
discovered) from the living institutional web presence of 16 endangered
North American languages through the corpus construction pipeline:
Common Crawl capture (S1, checked over 41 crawl releases spanning
2013--2026), language identification of the captured payloads (S2), a
FineWeb-2-style quality-filter cascade (S3), and presence in released
corpora (S4). Of the 36 pages Common Crawl captured, exactly one is
recognized as its language, and the filter cascade removes it; no
inventory domain contributes a document to any released per-language
subset examined.

## What is (and is not) released here

The repository releases the **inventory with per-URL provenance,
document-level metadata, and derived statistics only — never scraped
text**. Page and record caches are excluded by `.gitignore` and have
never been tracked.

**Correction and removal.** If you are a member or representative of one
of the nations whose languages are discussed here, or a steward of a site
in the inventory, and would like anything corrected or removed, please
open an issue in this repository; such requests will be honored.

## Layout

- `src/` — the full pipeline: inventory verification and deepening, CDX
  coverage (including the 41-crawl expansion), WARC retrieval + LID
  routing, filter-cascade simulation, released-corpus scans, corpus
  breadth check, PDF-surface count
- `src/plots/` — figure, table, and macro generators (read `results/`
  only; every number in the paper comes from these)
- `data/inventory/candidates.json` — the curated inventory with search
  provenance per entry
- `results/` — one JSON per experiment, with config recorded
- `figures/` — the generated figure (colorblind-safe vector PDF)
- `DATA.md` — every data source and its terms

## Reproducing

Python 3.11 with `fasttext`, `pandas`, `requests`, `matplotlib`.
GlotLID v3 (`cis-lmu/glotlid`, Apache 2.0) is public; point
`GLOTLID_MODEL` at the downloaded `model.bin`. Corpus subsets download
from Hugging Face (`HuggingFaceFW/fineweb-2`, `cis-lmu/GlotCC-V1`).
Common Crawl queries use the public CDX index and WARC range requests
with polite pacing; all responses are cached, so reruns are idempotent.

> Note: `git_hash` values recorded inside `results/*.json` refer to
> commits of the private development repository; all results are
> regenerable from the scripts.

## Citation

```bibtex
@inproceedings{goyal2026crawlgap,
  title     = {The Crawl Gap: Where Endangered-Language Web Content Is
               Lost Before It Reaches a Corpus},
  author    = {Goyal, Sharvin},
  booktitle = {Proceedings of the 13th Web-as-Corpus Workshop (WaC-13)},
  year      = {2026},
  address   = {Budapest, Hungary}
}
```

## License

Code: MIT (see `LICENSE`). Inventory and derived statistics: CC BY 4.0.
