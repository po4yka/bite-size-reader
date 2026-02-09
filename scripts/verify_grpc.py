#!/usr/bin/env python3
"""Test client for the ProcessingService gRPC server.

This script demonstrates usage of the ProcessingClient library.
"""

import argparse
import asyncio
import sys

from app.grpc import ProcessingClient, ProcessingUpdate, SyncProcessingClient


async def test_async_client(url: str, target: str) -> None:
    """Test the async client."""
    print(f"Testing async client: {url}")
    print("-" * 60)

    async with ProcessingClient(target) as client:
        try:
            result = await client.process_url(
                url,
                language="en",
                force_refresh=True,
                progress_callback=lambda u: print(
                    f"  [{u.progress:>3.0%}] {u.status:<10} {u.message}"
                ),
            )

            print("-" * 60)
            if result.is_success:
                print(f"✅ Success! Summary ID: {result.summary_id}")
                print(f"   Duration: {result.duration_seconds:.2f}s")
            else:
                print(f"❌ Failed: {result.error}")
                sys.exit(1)

        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)


def test_sync_client(url: str, target: str) -> None:
    """Test the sync client."""
    print(f"\nTesting sync client: {url}")
    print("-" * 60)

    with SyncProcessingClient(target) as client:
        try:
            result = client.process_url(url, language="en", force_refresh=True)

            print("-" * 60)
            if result.is_success:
                print(f"✅ Success! Summary ID: {result.summary_id}")
                print(f"   Duration: {result.duration_seconds:.2f}s")
            else:
                print(f"❌ Failed: {result.error}")
                sys.exit(1)

        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)


async def test_batch(urls: list[str], target: str) -> None:
    """Test batch processing."""
    print(f"\nTesting batch processing ({len(urls)} URLs)")
    print("-" * 60)

    def progress(url: str, update: ProcessingUpdate) -> None:
        short_url = url.replace("https://", "").replace("http://", "")[:30]
        print(f"  [{short_url:<30}] {update.progress:>3.0%} {update.status}")

    async with ProcessingClient(target) as client:
        results = await client.process_urls(
            urls,
            language="en",
            max_concurrent=3,
            progress_callback=progress,
        )

    print("-" * 60)
    success_count = sum(1 for r in results if r.is_success)
    print(f"Results: {success_count}/{len(results)} succeeded")

    for url, result in zip(urls, results, strict=False):
        status = "✅" if result.is_success else "❌"
        short_url = url.replace("https://", "").replace("http://", "")[:40]
        print(f"  {status} {short_url:<40} {result.status}")


def main():
    parser = argparse.ArgumentParser(description="Test ProcessingService gRPC client")
    parser.add_argument(
        "--target",
        default="localhost:50051",
        help="gRPC server target (default: localhost:50051)",
    )
    parser.add_argument(
        "--url",
        default="https://example.com",
        help="URL to process (default: https://example.com)",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Use synchronous client",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Test batch processing with multiple URLs",
    )

    args = parser.parse_args()

    if args.batch:
        test_urls = [
            "https://example.com",
            "https://httpbin.org/html",
            "https://news.ycombinator.com",
        ]
        asyncio.run(test_batch(test_urls, args.target))
    elif args.sync:
        test_sync_client(args.url, args.target)
    else:
        asyncio.run(test_async_client(args.url, args.target))


if __name__ == "__main__":
    main()
