#!/usr/bin/env python3
"""
DocuMind — Ingestion CLI
==========================
Command-line entry point for indexing document collections.

Usage:
    python ingest.py docs/kubernetes/                    # index a directory
    python ingest.py docs/aws-waf.pdf                   # index a single file
    python ingest.py docs/ --namespace kubernetes-docs  # named namespace
    python ingest.py docs/ --dry-run                    # parse + chunk, skip embedding

The --dry-run flag is useful for verifying chunking strategy
without consuming Voyage AI API credits.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env before importing anything that reads settings
load_dotenv()

from app.core.config import settings  # noqa: E402 — must be after load_dotenv
from app.rag.ingestion.pipeline import ingest_document  # noqa: E402

from ingestion.chunkers.header_aware import chunk_document  # noqa: E402
from ingestion.parsers import (  # noqa: E402
    is_supported,
    parse_document,  # noqa: E402
    supported_extensions,
)

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("ingest")


def collect_files(path: Path) -> list[Path]:
    """
    Collect all supported files from a path.
    If path is a file, return [path].
    If path is a directory, return all supported files recursively.
    """
    if path.is_file():
        if not is_supported(path):
            logger.error(
                f"Unsupported format: {path.suffix}. "
                f"Supported: {', '.join(supported_extensions())}"
            )
            sys.exit(1)
        return [path]

    if path.is_dir():
        files = [f for f in path.rglob("*") if f.is_file() and is_supported(f)]
        if not files:
            logger.error(
                f"No supported files found in {path}. "
                f"Supported extensions: {', '.join(supported_extensions())}"
            )
            sys.exit(1)
        # Sort for deterministic processing order
        return sorted(files)

    logger.error(f"Path does not exist: {path}")
    sys.exit(1)


async def run_ingestion(
    files: list[Path],
    namespace: str,
    dry_run: bool,
) -> None:
    """Process a list of files through the ingestion pipeline."""
    total = len(files)
    succeeded = 0
    failed: list[tuple[Path, str]] = []

    logger.info(
        "Starting ingestion",
        extra={"files": total, "namespace": namespace, "dry_run": dry_run},
    )

    for i, file_path in enumerate(files, start=1):
        logger.info(f"[{i}/{total}] Processing: {file_path.name}")

        if dry_run:
            # Parse + chunk only — verify strategy without API calls
            try:
                doc = parse_document(file_path)
                chunks = chunk_document(doc)
                logger.info(
                    f"  Dry run: {len(chunks)} chunks from {file_path.name}",
                    extra={"tokens": sum(c.metadata.token_count for c in chunks)},
                )
                # Show heading path distribution
                paths = [c.metadata.heading_path for c in chunks if c.metadata.heading_path]
                unique_paths = len(set(paths))
                logger.info(f"  Unique heading paths: {unique_paths}")
                succeeded += 1
            except Exception as exc:
                logger.error(f"  Dry run failed: {exc}")
                failed.append((file_path, str(exc)))
        else:
            try:
                result = await ingest_document(file_path, namespace=namespace)
                logger.info(
                    f"  Done: {result.chunk_count} chunks, "
                    f"{result.token_count:,} tokens, "
                    f"{result.duration_ms}ms"
                )
                succeeded += 1
            except Exception as exc:
                logger.error(f"  Failed: {exc}")
                failed.append((file_path, str(exc)))

    # Summary
    print(f"\n{'='*50}")
    print(f"  Ingestion {'(dry run) ' if dry_run else ''}complete")
    print(f"  Succeeded: {succeeded}/{total}")
    if failed:
        print(f"  Failed:    {len(failed)}/{total}")
        for path, error in failed:
            print(f"    {path.name}: {error}")
    print(f"  Namespace: {namespace}")
    print(f"{'='*50}\n")

    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DocuMind document ingestion CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ingest.py docs/kubernetes/
  python ingest.py docs/aws-waf.pdf --namespace aws-docs
  python ingest.py docs/ --dry-run
        """,
    )
    parser.add_argument(
        "path",
        type=Path,
        help="File or directory to ingest",
    )
    parser.add_argument(
        "--namespace",
        default="default",
        help="Pinecone namespace for this collection (default: 'default')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and chunk only — skip embedding and indexing. "
        "Use to verify chunking strategy without API costs.",
    )

    args = parser.parse_args()
    files = collect_files(args.path)

    print("\nDocuMind Ingestion")
    print(f"  Path:      {args.path}")
    print(f"  Files:     {len(files)}")
    print(f"  Namespace: {args.namespace}")
    print(f"  Dry run:   {args.dry_run}")
    print(f"  Supported: {', '.join(supported_extensions())}\n")

    asyncio.run(
        run_ingestion(
            files=files,
            namespace=args.namespace,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
