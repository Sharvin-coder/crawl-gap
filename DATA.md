# Data Sources & Licenses

| Source | What | Terms | Local location |
|---|---|---|---|
| Web search results (2026-08-11ff) + public directories | inventory candidate URLs, provenance in found_via | URLs/metadata only | data/inventory/candidates.json |
| Live sites in inventory | verification fetches (status + language evidence) | research use; text never committed | data/cache/live/ (not committed) |
| Common Crawl CDX API (index.commoncrawl.org) | capture records per URL/domain | CC ToU; polite sequential queries, cached | data/cache/cdx/ (not committed) |
| Common Crawl WARC range requests (data.commoncrawl.org) | individual page payloads for captured URLs | CC ToU | data/cache/warc/ (not committed) |
| cis-lmu/glotlid model.bin v3 (HF) | LID | Apache 2.0 | local model cache (not committed; set GLOTLID_MODEL) |
| HuggingFaceFW/fineweb-2 (HF) | S4 endpoint lookup (per-language subsets) | ODC-By 1.0, CC ToU | data/raw/ (not committed) |
| cis-lmu/GlotCC-V1 (HF) | S4 endpoint lookup | CC0 metadata, CC ToU | data/raw/ (not committed) |

Ethics posture: repo commits only URLs, metadata, annotations, and derived
statistics — never scraped text.
