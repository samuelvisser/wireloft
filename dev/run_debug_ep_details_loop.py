from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from wireloft_controller.tasks.workers.debug_ep_details.entrypoint import debug_ep_details


async def run_once(slug: str) -> None:
    """Run a single `debug_ep_details` invocation for the given show slug."""
    print("\n" + "=" * 60, flush=True)
    print(f"Starting debug_ep_details for slug='{slug}' at {datetime.now().isoformat()}", flush=True)

    try:
        # `resource_id` is optional; we call by slug only.
        await debug_ep_details(slug=slug, progress=None)
        print(f"Finished debug_ep_details at {datetime.now().isoformat()}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"debug_ep_details failed: {exc}", flush=True)


async def main(slug: str, interval_seconds: int = 60) -> None:
    """Continuously run the worker every `interval_seconds` seconds."""
    while True:
        await run_once(slug)
        print(f"Sleeping for {interval_seconds} seconds...", flush=True)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run debug_ep_details worker in a loop.")
    parser.add_argument("--slug", required=True, help="Show slug to debug (matches DW show slug)")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Interval in seconds between runs (default: 60)",
    )

    args = parser.parse_args()
    asyncio.run(main(slug=args.slug, interval_seconds=args.interval))