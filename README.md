# rag-eval-historical-newspapers

Evaluation corpus of digitized historical newspapers from Chronicling America (Library of Congress) for testing RAG systems.

## What This Is

This repository contains **evaluation data for RAG systems**:

- **corpus.yaml** - Evaluation scenarios (in each corpus directory)
- **metadata.json** - Page inventory with LOC identifiers
- **Generated questions** - Validated Q/A pairs (where available)

The actual newspaper files are not included. Use `download_newspapers.py` to fetch them from the Library of Congress.

## Quick Start

```bash
cd scripts
uv sync
uv run python download_newspapers.py prohibition_1920s --max-docs 5
```

## Available Corpora

| Corpus | Pages | Description |
|--------|-------|-------------|
| `prohibition_1920s` | 146 | 18th Amendment era coverage |
| `civil_war_union` | 150 | Northern newspapers 1861-1865 |
| `civil_war_confederate` | 150 | Southern newspapers 1861-1865 |
| `spanish_flu_1918` | 150 | Pandemic coverage 1918-1919 |
| `wwi_american` | 150 | US entry to armistice 1917-1918 |
| `gold_rush` | 150 | California Gold Rush 1848-1855 |
| `great_depression` | 150 | Economic crisis 1929-1939 |
| `womens_suffrage` | 142 | 19th Amendment lead-up 1910-1920 |

All corpora were built December 2025 from Chronicling America.

## Directory Structure

```
data/<corpus>/
    corpus.yaml         # Evaluation configuration
    metadata.json       # Page inventory
    pages/              # Downloaded files (gitignored)

scripts/
    download_newspapers.py  # Fetch pages from existing metadata
    build_corpus.py         # Build new corpora via LOC search
```

## Metadata Format

```json
{
  "corpus": "prohibition_1920s",
  "search_query": "prohibition",
  "start_date": "1920-01-01",
  "end_date": "1933-12-31",
  "state_filter": null,
  "total_pages": 146,
  "pages": [
    {
      "page_id": "sn85042345/1920-02-29/ed-1/seq-1",
      "newspaper_title": "The Morning Tulsa Daily World",
      "lccn": "sn85042345",
      "date": "1920-02-29",
      "edition": 1,
      "sequence": 1,
      "state": "oklahoma",
      "city": "tulsa",
      "batch_path": "ndnp/okhi/batch_okhi_hughes_ver01/...",
      "url": "https://www.loc.gov/resource/sn85042345/1920-02-29/ed-1/?sp=1",
      "files": {
        "pdf": "pages/sn85042345_1920-02-29_ed-1_seq-1.pdf",
        "jp2": "pages/sn85042345_1920-02-29_ed-1_seq-1.jp2",
        "xml": "pages/sn85042345_1920-02-29_ed-1_seq-1.xml",
        "txt": "pages/sn85042345_1920-02-29_ed-1_seq-1.txt"
      }
    }
  ]
}
```

## Downloading Pages

The download script fetches files from LOC storage based on existing metadata:

```bash
cd scripts
uv run python download_newspapers.py prohibition_1920s --max-docs 5
uv run python download_newspapers.py civil_war_union
```

| Option | Description |
|--------|-------------|
| `corpus` | Corpus name (e.g., prohibition_1920s) |
| `--max-docs` | Maximum pages to download (default: all) |
| `--delay` | Delay between requests in seconds (default: 1.0) |

Each page downloads 4 files: PDF, JP2, XML, and TXT (~2-5MB total per page).

## Building New Corpora

The build script searches Chronicling America and creates new corpora:

```bash
cd scripts
uv run python build_corpus.py "prohibition" --corpus prohibition_1920s \
    --start-date 1920-01-01 --end-date 1933-12-31 --max-pages 150
```

| Option | Description |
|--------|-------------|
| `query` | Search query for Chronicling America (required) |
| `--corpus` | Corpus directory name (required) |
| `--max-pages` | Maximum pages to download (default: 150) |
| `--start-date` | Start date filter (YYYY-MM-DD) |
| `--end-date` | End date filter (YYYY-MM-DD) |
| `--state` | State filter |
| `--data-dir` | Output directory (default: ../data/) |

## Licensing

**This repository**: MIT License

**Newspaper content**: Public domain (digitized historical newspapers)

The Chronicling America collection is a project of the [National Digital Newspaper Program](https://www.loc.gov/ndnp/), a partnership between the Library of Congress and the National Endowment for the Humanities.
