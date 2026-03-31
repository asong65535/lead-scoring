"""Basic load test for the scoring endpoint.

Measures throughput and latency percentiles against a running server.

Usage:
    poetry run python scripts/load_test.py [--base-url URL] [--requests N] [--concurrency C]

Defaults: 200 requests, 10 concurrent workers, http://localhost:8000

Requires: A running server with seeded data.
"""

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import psycopg2

from config.settings import get_settings


def _fetch_lead_ids(limit: int) -> list[str]:
    """Fetch lead IDs directly from the database."""
    settings = get_settings()
    sync_url = settings.database.url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM leads LIMIT %s", (limit,))
            return [str(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()


async def run_load_test(base_url: str, total_requests: int, concurrency: int):
    """Fire concurrent scoring requests and collect latency measurements."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        resp = await client.get("/health")
        if resp.status_code != 200:
            print(f"Server not healthy: {resp.status_code}")
            return

    lead_ids = _fetch_lead_ids(limit=max(concurrency, 20))
    if not lead_ids:
        print("No leads found in database. Seed data first.")
        return
    print(f"Loaded {len(lead_ids)} lead IDs from database")

    latencies: list[float] = []
    errors = 0
    semaphore = asyncio.Semaphore(concurrency)

    async def score_one(client: httpx.AsyncClient, lead_id: str):
        nonlocal errors
        async with semaphore:
            start = time.perf_counter()
            try:
                resp = await client.post(f"/score/{lead_id}")
                elapsed = time.perf_counter() - start
                if resp.status_code == 200:
                    latencies.append(elapsed)
                else:
                    errors += 1
            except httpx.HTTPError:
                errors += 1

    print(f"Load test: {total_requests} requests, {concurrency} concurrent")
    print(f"Target: {base_url}")
    print()

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        wall_start = time.perf_counter()
        tasks = []
        for i in range(total_requests):
            lid = lead_ids[i % len(lead_ids)]
            tasks.append(score_one(client, lid))
        await asyncio.gather(*tasks)
        wall_elapsed = time.perf_counter() - wall_start

    if not latencies:
        print(f"All {total_requests} requests failed.")
        return

    latencies.sort()
    n = len(latencies)

    print(f"Completed: {n}/{total_requests} ({errors} errors)")
    print(f"Wall time: {wall_elapsed:.2f}s")
    print(f"Throughput: {n / wall_elapsed:.1f} req/s")
    print()
    print("Latency (seconds):")
    print(f"  Min:    {latencies[0]:.4f}")
    print(f"  Median: {latencies[n // 2]:.4f}")
    print(f"  P90:    {latencies[int(n * 0.90)]:.4f}")
    print(f"  P95:    {latencies[int(n * 0.95)]:.4f}")
    print(f"  P99:    {latencies[int(n * 0.99)]:.4f}")
    print(f"  Max:    {latencies[-1]:.4f}")
    print(f"  Mean:   {statistics.mean(latencies):.4f}")
    if n > 1:
        print(f"  Stddev: {statistics.stdev(latencies):.4f}")


def main():
    parser = argparse.ArgumentParser(description="Load test the scoring endpoint")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Server base URL")
    parser.add_argument("--requests", type=int, default=200, help="Total requests to send")
    parser.add_argument("--concurrency", type=int, default=10, help="Max concurrent requests")
    args = parser.parse_args()

    asyncio.run(run_load_test(args.base_url, args.requests, args.concurrency))


if __name__ == "__main__":
    main()
