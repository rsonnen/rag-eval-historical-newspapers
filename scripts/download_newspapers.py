#!/usr/bin/env python3
"""Download newspaper pages from a curated corpus.

Reads metadata.json and downloads all files from LOC storage.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from tqdm import tqdm

TILE_STORAGE_URL = "https://tile.loc.gov/storage-services/service"
TEXT_SERVICES_URL = "https://tile.loc.gov/text-services/word-coordinates-service"


def download_corpus(
    corpus_dir: Path,
    delay: float = 1.0,
    max_docs: int | None = None,
) -> None:
    """Download newspaper pages in a corpus from LOC storage.

    Args:
        corpus_dir: Path to corpus directory containing metadata.json.
        delay: Seconds to wait between downloads.
        max_docs: Maximum number of pages to download (None for all).
    """
    metadata_path = corpus_dir / "metadata.json"
    if not metadata_path.exists():
        print(f"Error: {metadata_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(metadata_path, encoding="utf-8") as f:
        metadata: dict[str, Any] = json.load(f)

    pages_dir = corpus_dir / "pages"
    pages_dir.mkdir(exist_ok=True)

    pages: list[dict[str, Any]] = metadata.get("pages", [])
    if max_docs is not None:
        pages = pages[:max_docs]

    print(f"Downloading {len(pages)} pages to {pages_dir}")

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        for page in tqdm(pages, desc="Downloading", unit="page"):
            batch_path: str = page["batch_path"]
            files: dict[str, str] = page.get("files", {})

            for fmt, local_path in files.items():
                if local_path is None:
                    continue

                output_path = corpus_dir / local_path
                if output_path.exists():
                    continue

                output_path.parent.mkdir(parents=True, exist_ok=True)

                if fmt == "txt":
                    url = (
                        f"{TEXT_SERVICES_URL}?segment=/service/{batch_path}.xml"
                        "&format=alto_xml&full_text=1"
                    )
                    try:
                        response = client.get(url)
                        response.raise_for_status()
                        data = response.json()
                        segment_data = next(iter(data.values()))
                        full_text = segment_data.get("full_text", "")
                        output_path.write_text(full_text, encoding="utf-8")
                    except (httpx.HTTPError, json.JSONDecodeError, StopIteration) as e:
                        tqdm.write(f"Error downloading {fmt}: {e}")
                else:
                    url = f"{TILE_STORAGE_URL}/{batch_path}.{fmt}"
                    try:
                        response = client.get(url)
                        response.raise_for_status()
                        output_path.write_bytes(response.content)
                    except httpx.HTTPError as e:
                        tqdm.write(f"Error downloading {fmt}: {e}")

                time.sleep(delay)

    print("Done")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Download newspaper pages from a curated corpus")
    parser.add_argument("corpus", help="Corpus directory (e.g., prohibition_1920s)")
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between requests in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=None,
        help="Maximum number of pages to download (default: all)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    corpus_dir = repo_root / "data" / args.corpus

    if not corpus_dir.exists():
        print(f"Error: Corpus directory not found: {corpus_dir}", file=sys.stderr)
        sys.exit(1)

    download_corpus(corpus_dir, args.delay, args.max_docs)


if __name__ == "__main__":
    main()
