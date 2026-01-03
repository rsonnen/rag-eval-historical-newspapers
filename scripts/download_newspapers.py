#!/usr/bin/env python
"""Download historical newspapers from Chronicling America.

A CLI tool that downloads digitized newspaper pages from the Library of Congress
Chronicling America collection. Downloads all 4 formats per page (PDF, JP2, TXT, XML)
to test document-processor's handling of OCR errors, multi-column layouts, and
historical typography.

Usage:
    uv run python download_newspapers.py "prohibition" --corpus prohibition_1920s
        --start-date 1920-01-01 --end-date 1929-12-31 --max-pages 150

Output:
    <data-dir>/<corpus>/
        pages/          - All format files per page (PDF, JP2, TXT, XML)
        metadata.json   - Page metadata for all downloaded documents

API Notes:
    - Search: https://www.loc.gov/collections/chronicling-america/?dl=page&fo=json
    - Files: https://tile.loc.gov/storage-services/service/ndnp/{batch_path}.{ext}
    - Rate limits: 20 req/min burst, 20 req/10sec crawl
    - All content is public domain
"""

import argparse
import contextlib
import json
import logging
import random
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

LOC_SEARCH_URL = "https://www.loc.gov/collections/chronicling-america/"
TILE_STORAGE_URL = "https://tile.loc.gov/storage-services/service"
TEXT_SERVICES_URL = "https://tile.loc.gov/text-services/word-coordinates-service"

# Rate limiting - LOC allows 20/min burst, 20/10sec crawl
BASE_DELAY_SECONDS = 0.5
MAX_RETRIES = 8
BACKOFF_FACTOR = 2.0
MAX_BACKOFF_SECONDS = 300


def request_with_retry(
    client: httpx.Client,
    url: str,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    """Make an HTTP request with exponential backoff on errors."""
    delay = BASE_DELAY_SECONDS
    last_exception: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            jitter = random.uniform(0, delay * 0.1)  # noqa: S311 - not crypto
            sleep_time = delay + jitter
            logger.info(f"Retry {attempt}/{MAX_RETRIES}, waiting {sleep_time:.1f}s")
            time.sleep(sleep_time)
            delay = min(delay * BACKOFF_FACTOR, MAX_BACKOFF_SECONDS)
        else:
            time.sleep(BASE_DELAY_SECONDS)

        try:
            response = client.get(url, params=params, follow_redirects=True)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    with contextlib.suppress(ValueError):
                        delay = max(float(retry_after), delay)
                last_exception = httpx.HTTPStatusError(
                    "Rate limited (429)", request=response.request, response=response
                )
                continue

            if response.status_code >= 500:
                last_exception = httpx.HTTPStatusError(
                    f"Server error ({response.status_code})",
                    request=response.request,
                    response=response,
                )
                continue

            response.raise_for_status()
            return response

        except httpx.TimeoutException as e:
            last_exception = e
            logger.warning(f"Timeout: {e}")
            continue
        except httpx.RequestError as e:
            last_exception = e
            logger.warning(f"Request failed: {e}")
            continue

    if last_exception:
        raise last_exception
    raise httpx.HTTPError("All retries exhausted")


def extract_batch_path(image_url: str) -> str | None:
    """Extract the batch storage path from an IIIF image URL.

    Example input:
        https://tile.loc.gov/image-services/iiif/service:ndnp:dlc:batch_dlc_fogler_ver01:data:sn83030214:00206532518:1920050201:0027/full/...

    Returns:
        ndnp/dlc/batch_dlc_fogler_ver01/data/sn83030214/00206532518/1920050201/0027
    """
    match = re.search(r"service:([^/]+)/full", image_url)
    if not match:
        return None
    # Convert colon-separated path to slash-separated
    return match.group(1).replace(":", "/")


def _get_first_str(items: list[str], default: str) -> str:
    """Get first element from a list or return default."""
    return items[0] if items else default


def _parse_page_result(item: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a single search result item into page metadata.

    Returns None if the item is not a valid page result.
    """
    # Must be a page (segment) result
    if item.get("type") != ["segment"]:
        return None

    # Extract batch path from image URL
    image_urls = item.get("image_url", [])
    if not image_urls:
        return None

    batch_path = extract_batch_path(image_urls[0])
    if not batch_path:
        return None

    lccn = _get_first_str(item.get("number_lccn", []), "unknown")
    date = item.get("date", "unknown")
    edition = _get_first_str(item.get("number_edition", ["1"]), "1")

    page_num_str = _get_first_str(item.get("number_page", ["1"]), "1")
    sequence = int(page_num_str.lstrip("0") or "1")

    return {
        "page_id": f"{lccn}/{date}/ed-{edition}/seq-{sequence}",
        "newspaper_title": _get_first_str(item.get("partof_title", []), "Unknown"),
        "lccn": lccn,
        "date": date,
        "edition": int(edition),
        "sequence": sequence,
        "state": _get_first_str(item.get("location_state", ["Unknown"]), "Unknown"),
        "city": _get_first_str(item.get("location_city", ["Unknown"]), "Unknown"),
        "batch_path": batch_path,
        "ocr_text": _get_first_str(item.get("description", []), ""),
        "url": item.get("url", ""),
    }


def _build_date_param(start_date: str | None, end_date: str | None) -> str | None:
    """Build LOC API dates parameter from start/end dates.

    LOC API uses slash-separated years (YYYY/YYYY).
    """
    if start_date and end_date:
        return f"{start_date[:4]}/{end_date[:4]}"
    if start_date:
        return f"{start_date[:4]}/{start_date[:4]}"
    if end_date:
        return f"{end_date[:4]}/{end_date[:4]}"
    return None


def _build_search_params(
    query: str,
    start_date: str | None,
    end_date: str | None,
    state: str | None,
) -> dict[str, str | int]:
    """Build search parameters for LOC API."""
    params: dict[str, str | int] = {
        "fo": "json",
        "c": 100,
        "dl": "page",  # Critical: search at page level to get file URLs
        "qs": query,
        "fa": "partof_collection:chronicling america",
    }

    dates_param = _build_date_param(start_date, end_date)
    if dates_param:
        params["dates"] = dates_param
    if state:
        params["location_state"] = state.lower()

    return params


def search_pages(
    client: httpx.Client,
    query: str,
    max_pages: int,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    state: str | None = None,
) -> list[dict[str, Any]]:
    """Search Chronicling America for newspaper pages matching a query."""
    pages: list[dict[str, Any]] = []
    params = _build_search_params(query, start_date, end_date, state)
    page_num = 1

    with tqdm(total=max_pages, desc="Searching", unit="pages") as pbar:
        while len(pages) < max_pages:
            params["sp"] = page_num

            try:
                response = request_with_retry(client, LOC_SEARCH_URL, params=params)
                data = response.json()
            except httpx.HTTPError as e:
                logger.error(f"Search failed: {e}")
                break
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                break

            results = data.get("results", [])
            if not results:
                logger.info("No more results")
                break

            for item in results:
                if len(pages) >= max_pages:
                    break

                page_data = _parse_page_result(item)
                if page_data is None:
                    continue

                pages.append(page_data)
                pbar.update(1)

            # Check pagination
            pagination = data.get("pagination", {})
            if not pagination.get("next"):
                break

            page_num += 1

    return pages


def build_file_urls(page: dict[str, Any]) -> dict[str, str]:
    """Build download URLs for all formats.

    Uses tile.loc.gov/storage-services for PDF, JP2, XML.
    Uses tile.loc.gov/text-services for TXT (OCR full text via Text Services API).
    """
    batch_path = page["batch_path"]
    return {
        "pdf": f"{TILE_STORAGE_URL}/{batch_path}.pdf",
        "jp2": f"{TILE_STORAGE_URL}/{batch_path}.jp2",
        "xml": f"{TILE_STORAGE_URL}/{batch_path}.xml",
        "txt": (
            f"{TEXT_SERVICES_URL}?segment=/service/{batch_path}.xml"
            "&format=alto_xml&full_text=1"
        ),
    }


def build_local_paths(page: dict[str, Any]) -> dict[str, str]:
    """Build local file paths for all formats."""
    lccn = page["lccn"]
    date = page["date"]
    ed = page["edition"]
    seq = page["sequence"]
    base = f"{lccn}_{date}_ed-{ed}_seq-{seq}"
    return {
        "pdf": f"{base}.pdf",
        "jp2": f"{base}.jp2",
        "txt": f"{base}.txt",
        "xml": f"{base}.xml",
    }


def download_file(client: httpx.Client, url: str, output_path: Path) -> bool:
    """Download a binary file (PDF, JP2, XML)."""
    try:
        response = request_with_retry(client, url)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        return True
    except httpx.HTTPError as e:
        logger.debug(f"Failed: {url}: {e}")
        return False


def download_text_file(client: httpx.Client, url: str, output_path: Path) -> bool:
    """Download OCR text via Text Services API.

    The Text Services API returns JSON with structure:
    {"/service/{batch_path}.xml": {"full_text": "...", "height": "...", "width": "..."}}

    This function extracts the full_text field and saves it as plain text.
    """
    try:
        response = request_with_retry(client, url)
        data = response.json()

        # Extract full_text from the first (and only) key in the response
        if not data:
            logger.debug(f"Empty response from Text Services: {url}")
            return False

        # The response has a single key which is the segment path
        segment_data = next(iter(data.values()))
        full_text = segment_data.get("full_text", "")

        if not full_text:
            logger.debug(f"No full_text in response: {url}")
            return False

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(full_text, encoding="utf-8")
        return True

    except json.JSONDecodeError as e:
        logger.debug(f"Invalid JSON from Text Services: {url}: {e}")
        return False
    except httpx.HTTPError as e:
        logger.debug(f"Failed: {url}: {e}")
        return False


def download_page_files(
    client: httpx.Client,
    page: dict[str, Any],
    pages_dir: Path,
) -> dict[str, str | None]:
    """Download all format files for a newspaper page.

    Uses download_file() for binary formats (PDF, JP2, XML).
    Uses download_text_file() for TXT (Text Services API returns JSON).
    """
    urls = build_file_urls(page)
    local_paths = build_local_paths(page)
    downloaded: dict[str, str | None] = {}

    for fmt in ["pdf", "jp2", "xml", "txt"]:
        output_path = pages_dir / local_paths[fmt]
        if output_path.exists():
            downloaded[fmt] = f"pages/{local_paths[fmt]}"
            continue

        # TXT uses Text Services API (JSON response), others are binary
        if fmt == "txt":
            success = download_text_file(client, urls[fmt], output_path)
        else:
            success = download_file(client, urls[fmt], output_path)

        downloaded[fmt] = f"pages/{local_paths[fmt]}" if success else None

    return downloaded


def download_corpus(
    query: str,
    corpus_name: str,
    data_dir: Path,
    max_pages: int,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    state: str | None = None,
) -> None:
    """Download a corpus of newspaper pages."""
    corpus_dir = data_dir / corpus_name
    pages_dir = corpus_dir / "pages"
    metadata_path = corpus_dir / "metadata.json"

    pages_dir.mkdir(parents=True, exist_ok=True)

    # Load existing metadata for resume
    existing_metadata: dict[str, dict[str, Any]] = {}
    if metadata_path.exists():
        with metadata_path.open(encoding="utf-8") as f:
            existing_data = json.load(f)
            existing_metadata = {
                item["page_id"]: item for item in existing_data.get("pages", [])
            }
        logger.info(f"Found {len(existing_metadata)} existing pages")

    headers = {"User-Agent": "BiteSizeRAG-Corpus-Builder/1.0 (historical research)"}

    with httpx.Client(headers=headers, timeout=120.0) as client:
        logger.info(f"Searching: {query}")

        pages = search_pages(
            client,
            query,
            max_pages=max_pages,
            start_date=start_date,
            end_date=end_date,
            state=state,
        )

        logger.info(f"Found {len(pages)} pages")

        downloaded = 0
        skipped = 0
        partial = 0

        for page in tqdm(pages, desc="Downloading", unit="pages"):
            page_id = page["page_id"]

            if page_id in existing_metadata:
                existing_files = existing_metadata[page_id].get("files", {})
                if all(existing_files.get(fmt) for fmt in ["pdf", "jp2", "txt", "xml"]):
                    skipped += 1
                    continue

            files = download_page_files(client, page, pages_dir)

            # Remove ocr_text from stored metadata (too large)
            page_copy = {k: v for k, v in page.items() if k != "ocr_text"}
            page_copy["files"] = files

            successful = sum(1 for v in files.values() if v is not None)
            if successful == 4:
                downloaded += 1
            elif successful > 0:
                partial += 1

            existing_metadata[page_id] = page_copy

        # Save metadata
        metadata = {
            "corpus": corpus_name,
            "search_query": query,
            "start_date": start_date,
            "end_date": end_date,
            "state_filter": state,
            "total_pages": len(existing_metadata),
            "pages": list(existing_metadata.values()),
        }

        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"Downloaded: {downloaded}, Skipped: {skipped}, Partial: {partial}")
        logger.info(f"Total: {len(existing_metadata)} pages in {corpus_dir}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download historical newspapers from Chronicling America",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run python download_newspapers.py "prohibition" --corpus prohibition_1920s \\
        --start-date 1920-01-01 --end-date 1929-12-31

    uv run python download_newspapers.py "influenza epidemic" \\
        --corpus spanish_flu_1918 --start-date 1918-01-01 --end-date 1919-12-31
        """,
    )
    parser.add_argument("query", type=str, help="Search query")
    parser.add_argument(
        "--corpus", type=str, required=True, help="Corpus directory name"
    )
    parser.add_argument(
        "--max-pages", type=int, default=150, help="Max pages (default: 150)"
    )
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--state", type=str, help="State filter")
    parser.add_argument(
        "--data-dir", type=Path, help="Data directory (default: ../data/)"
    )

    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    data_dir = args.data_dir or (script_dir.parent / "data")
    data_dir.mkdir(parents=True, exist_ok=True)

    try:
        download_corpus(
            query=args.query,
            corpus_name=args.corpus,
            data_dir=data_dir,
            max_pages=args.max_pages,
            start_date=args.start_date,
            end_date=args.end_date,
            state=args.state,
        )
        logger.info("Download complete!")
    except KeyboardInterrupt:
        logger.warning("\nInterrupted. Progress saved. Re-run to resume.")
        sys.exit(130)


if __name__ == "__main__":
    main()
