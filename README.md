# rag-eval-historical-newspapers

Evaluation corpus of digitized historical newspapers from Chronicling America (Library of Congress) for testing RAG systems and document processors.

## What This Is

This repository contains **evaluation data for RAG systems**:

- **corpus.yaml** - Evaluation configuration defining domain context and testing scenarios
- **Generated questions** - Validated Q/A pairs for evaluation (where available)
- **metadata.json** - Page inventory with LOC identifiers
- **Download script** - Fetches pages in multiple formats (PDF, JP2, TXT, XML)

The actual newspaper files are not included - they are public domain works hosted by the Library of Congress. Use the download script to fetch them.

## Purpose

Historical newspapers are a challenging real-world use case for document processing. This corpus tests document-processor's handling of:

- **OCR errors**: Variable quality due to age, printing quality, and paper condition
- **Multi-column layouts**: Complex newspaper page structures with mixed content
- **Historical typography**: Old fonts, printing styles, and period-specific formatting
- **Mixed content regions**: Advertisements, articles, images interspersed on pages
- **Period-specific language**: Archaic vocabulary, historical terminology

The LOC's pre-extracted OCR text (TXT/XML files) serves as ground truth for comparing document-processor's extraction quality against pages processed from PDF/JP2 images.

## Usage

```bash
# Install dependencies
cd scripts
uv sync

# Download a corpus (downloads all 4 formats per page: PDF, JP2, TXT, XML)
uv run python download_newspapers.py "prohibition" --corpus prohibition_1920s \
    --start-date 1920-01-01 --end-date 1929-12-31 --max-pages 150

uv run python download_newspapers.py "influenza epidemic" --corpus spanish_flu_1918 \
    --start-date 1918-01-01 --end-date 1919-12-31 --max-pages 150

uv run python download_newspapers.py "gold rush" --corpus gold_rush \
    --start-date 1848-01-01 --end-date 1855-12-31 --state california --max-pages 150

# Specify output directory
uv run python download_newspapers.py "war kaiser" --corpus wwi_american \
    --start-date 1917-01-01 --end-date 1918-11-11 --data-dir /path/to/data
```

## Output Structure

```
data/<corpus>/
    corpus.yaml                         # Evaluation configuration
    metadata.json                       # Page metadata for all downloads
    pages/                              # All format files per page (gitignored)
        sn84026749_1920-01-15_ed-1_seq-1.pdf   # Scanned page image
        sn84026749_1920-01-15_ed-1_seq-1.jp2   # High-res JPEG2000
        sn84026749_1920-01-15_ed-1_seq-1.txt   # Plain OCR text
        sn84026749_1920-01-15_ed-1_seq-1.xml   # ALTO XML with coordinates
        ...

scripts/
    download_newspapers.py              # Fetch pages from LOC
```

### File Formats

| Format | Extension | Purpose |
|--------|-----------|---------|
| PDF | `.pdf` | Scanned page image with embedded OCR layer |
| JP2 | `.jp2` | High-resolution JPEG2000 image |
| TXT | `.txt` | LOC's plain text OCR output |
| XML | `.xml` | ALTO XML with word coordinates |

### Corpus Organization (Future Step)

This script downloads all 4 formats into a single directory structure. A later step should organize these into **separate corpora per format** for testing different document-processor input pathways:

```
prohibition_1920s_pdf/    → Tests PDF ingestion
prohibition_1920s_jp2/    → Tests JP2 image ingestion (if supported)
prohibition_1920s_txt/    → Tests plain text ingestion
prohibition_1920s_xml/    → Tests ALTO XML ingestion (if supported)
```

Each format corpus tests document-processor's handling of that specific input type. You do NOT feed 4 formats of the same page into one corpus - that's 4 separate corpora, each with the same content in different formats.

This organization logic belongs in the evaluation pipeline, not in this download tooling. The download script just acquires all available formats.

### Metadata Format

```json
{
  "corpus": "prohibition_1920s",
  "search_query": "prohibition",
  "start_date": "1920-01-01",
  "end_date": "1929-12-31",
  "state_filter": null,
  "total_pages": 150,
  "pages": [
    {
      "page_id": "sn84026749/1920-01-15/ed-1/seq-1",
      "newspaper_title": "The San Francisco Call",
      "lccn": "sn84026749",
      "date": "1920-01-15",
      "edition": 1,
      "sequence": 1,
      "state": "California",
      "city": "San Francisco",
      "url": "https://chroniclingamerica.loc.gov/lccn/sn84026749/1920-01-15/ed-1/seq-1/",
      "files": {
        "pdf": "pages/sn84026749_1920-01-15_ed-1_seq-1.pdf",
        "jp2": "pages/sn84026749_1920-01-15_ed-1_seq-1.jp2",
        "txt": "pages/sn84026749_1920-01-15_ed-1_seq-1.txt",
        "xml": "pages/sn84026749_1920-01-15_ed-1_seq-1.xml"
      }
    }
  ]
}
```

## Suggested Corpora

Create these topic-focused corpora (150 pages each, ~300-750MB per corpus):

| Corpus | Search Query | Date Range | Notes |
|--------|--------------|------------|-------|
| `prohibition_1920s` | `prohibition` or `volstead` | 1920-1933 | 18th Amendment era |
| `civil_war_union` | `war rebellion confederate` | 1861-1865 | Northern newspapers |
| `civil_war_confederate` | `war yankee invasion` | 1861-1865 | Southern newspapers |
| `spanish_flu_1918` | `influenza epidemic flu` | 1918-1919 | Pandemic coverage |
| `wwi_american` | `war kaiser germany` | 1917-1918 | US entry to armistice |
| `gold_rush` | `gold miners california` | 1848-1855 | California Gold Rush |
| `great_depression` | `unemployment relief depression` | 1929-1939 | Economic crisis |
| `womens_suffrage` | `suffrage women vote` | 1910-1920 | 19th Amendment lead-up |

## Features

- **Downloads all 4 formats**: PDF, JP2, TXT, XML per page (~2-5MB total per page)
- **Resumable downloads**: Re-run the same command to continue interrupted downloads
- **Rate limiting**: Conservative 3-second delays with exponential backoff
- **Metadata tracking**: All page metadata saved for downstream processing

## API Details

Uses the Library of Congress JSON API and Text Services:

- **Search**: `GET https://www.loc.gov/collections/chronicling-america/?fo=json&dl=page`
- **PDF/JP2/XML**: `https://tile.loc.gov/storage-services/service/{batch_path}.{ext}`
- **OCR Text**: `https://tile.loc.gov/text-services/word-coordinates-service?segment=/service/{batch_path}.xml&format=alto_xml&full_text=1`
- **Pagination**: Page-based via `sp` parameter
- **Rate limits**: 20 requests/minute burst, 20 requests/10 seconds crawl

Note: The `batch_path` is extracted from IIIF image URLs in search results and used to construct file download URLs. The older `chroniclingamerica.loc.gov/lccn/.../ocr.txt` endpoint is deprecated and returns 404 for many pages.

## Licensing

**This repository** (scripts, configurations): MIT License

**Newspaper content**: Public domain (digitized historical newspapers with no copyright restrictions)

The Chronicling America collection is a project of the [National Digital Newspaper Program](https://www.loc.gov/ndnp/), a partnership between the Library of Congress and the National Endowment for the Humanities.

## OCR Quality Notes

OCR quality varies significantly based on:

- **Age of original**: Older papers often have degraded print quality
- **Paper condition**: Yellowing, tears, and stains affect recognition
- **Typography**: Period-specific fonts and printing techniques
- **Layout complexity**: Multi-column layouts with mixed content

This variability is intentional - it tests document-processor's robustness against real-world historical documents.

## Requirements

- Python 3.11+
- Dependencies: `httpx`, `tqdm` (see pyproject.toml)

## Storage Estimate

- Per page: ~2-5MB (4 files)
- Per corpus (150 pages): ~300-750MB
- Full collection (8 corpora): ~2.4-6GB
