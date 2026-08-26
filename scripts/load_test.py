"""A load test of the durable send path — the same three-phase send
(services/worker/tasks/send.py) the durability suite exercises, but at a
scale meant to surface throughput and contention issues a 6-job unit test
cannot: many concurrent claims racing the same small set of rows, and a
sustained volume closer to what a real campaign launch would produce.

This is NOT a substitute for tests/test_durability.py — it complements it.
The durability suite proves CORRECTNESS (no duplicates, ever, even under
adversarial crash timing). This proves the same correctness property still
holds at throughput, and reports latency/throughput numbers worth knowing
before a real deploy.

Run: uv run python scripts/load_test.py [--jobs N] [--concurrency N]
"""

from __future__ import annotations

import argparse
import asyncio
import time

from packages.shared.providers.fake import ChaosConfig, FakeEmailProvider
from packages.shared.transitions import SendStatus
from services.worker.tasks.send import send_email_task
from tests.test_durability import InMemoryJobStore, make_jobs


async def _run_one_job(job_id, store, provider, worker_id: str) -> tuple[bool, float]:
    """Drives one job to completion (or exhausts a small retry budget),
    returns (succeeded, latency_seconds)."""
    start = time.monotonic()
    for attempt in range(1, 6):
        try:
            outcome = await send_email_task(
                {"email_job_id": str(job_id), "campaign_id": "load_test"},
                store=store, provider=provider, worker_id=f"{worker_id}-a{attempt}",
                from_addr="loadtest@sendrun.test", attempt=attempt,
            )
            return outcome.status == SendStatus.SENT, time.monotonic() - start
        except Exception:
            continue
    return False, time.monotonic() - start


async def run_load_test(n_jobs: int, concurrency: int, chaos: ChaosConfig) -> None:
    print(f"Load test: {n_jobs:,} jobs, concurrency={concurrency}, seed={chaos.seed}")
    print(f"Chaos: transient={chaos.transient_error_rate:.1%} "
          f"permanent={chaos.permanent_error_rate:.1%} "
          f"latency={chaos.latency_ms}ms")

    jobs = make_jobs(n_jobs)
    store = InMemoryJobStore(jobs)
    provider = FakeEmailProvider(chaos)

    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_run(job_id):
        async with semaphore:
            return await _run_one_job(job_id, store, provider, "load_test_worker")

    start = time.monotonic()
    results = await asyncio.gather(*[bounded_run(jid) for jid in jobs])
    elapsed = time.monotonic() - start

    successes = sum(1 for ok, _ in results if ok)
    failures = n_jobs - successes
    latencies = sorted(lat for _, lat in results)
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0

    print(f"\n{'='*60}")
    print(f"Completed in {elapsed:.2f}s ({n_jobs / elapsed:.1f} jobs/sec)")
    print(f"Succeeded: {successes:,} / {n_jobs:,} ({successes / n_jobs:.1%})")
    print(f"Failed (exhausted retries): {failures:,}")
    print(f"Latency  p50={p50*1000:.1f}ms  p95={p95*1000:.1f}ms  p99={p99*1000:.1f}ms")
    print(f"\nProvider calls: {provider.send_calls}")
    print(f"Unique messages sent: {provider.provider_sends}")
    print(f"Idempotent replays (crash-recovery hits): {provider.idempotent_replays}")
    # THE assertion that matters. A load test that doesn't check this isn't
    # actually testing the thing this project defends.
    print(f"Duplicate sends: {provider.duplicate_sends}")
    print(f"{'='*60}")

    if provider.duplicate_sends != 0:
        print("\n❌ FAILED: duplicate sends detected under load.")
        raise SystemExit(1)
    print("\n✓ PASSED: zero duplicate sends under load.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=2000)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--transient-rate", type=float, default=0.08,
        help="Fraction of sends that fail transiently (retried)",
    )
    args = parser.parse_args()

    chaos = ChaosConfig(
        seed=args.seed,
        transient_error_rate=args.transient_rate,
        permanent_error_rate=0.01,
        latency_ms=(5, 30),  # kept small so the test finishes quickly
        webhook_before_send_ack_rate=0.0,  # webhook path isn't under test here
    )
    asyncio.run(run_load_test(args.jobs, args.concurrency, chaos))


if __name__ == "__main__":
    main()
