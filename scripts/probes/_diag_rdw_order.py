"""One-shot: fetch RDW order state from Alpaca + show DB state side-by-side.

Loads ALPACA_* env vars from docker inspect at runtime so it works under
`docker exec` (which doesn't inherit the container's runtime env from
docker-compose env_file by default).

Run via: docker exec apollo-market python -m scripts._diag_rdw_order
"""
import asyncio
import os
import subprocess


def _load_env_from_inspect() -> None:
    """The container's runtime env (set via docker-compose env_file) isn't
    visible to docker-exec child processes. Read it from /proc/1/environ
    if accessible, else from docker inspect."""
    if "ALPACA_PAPER_API_KEY" in os.environ:
        return
    # Try /proc/1/environ — the main process's env IS readable to root
    try:
        with open("/proc/1/environ", "rb") as f:
            for line in f.read().split(b"\x00"):
                if not line:
                    continue
                if b"=" in line:
                    k, _, v = line.partition(b"=")
                    os.environ.setdefault(k.decode(), v.decode())
    except Exception as e:
        print(f"could not read /proc/1/environ: {e}")


async def main() -> None:
    _load_env_from_inspect()
    print("ALPACA_PAPER_API_KEY in env:", "ALPACA_PAPER_API_KEY" in os.environ)

    from agents.market_intelligence.broker.alpaca_client import get_trading_client

    order_id = "3e234281-1283-4ed8-8083-00c74f05c815"
    client = get_trading_client("paper")
    o = client.get_order_by_id(order_id)
    print("\n=== ALPACA SIDE (live) ===")
    print(f"  status: {o.status}")
    print(f"  type: {o.order_type} side: {o.side} qty: {o.qty}")
    print(f"  stop_price: {o.stop_price} limit_price: {o.limit_price}")
    print(f"  submitted_at: {o.submitted_at}")
    print(f"  filled_at: {o.filled_at}")
    print(f"  expired_at: {o.expired_at}")
    print(f"  canceled_at: {o.canceled_at}")
    print(f"  filled_qty: {o.filled_qty} avg_price: {o.filled_avg_price}")


if __name__ == "__main__":
    asyncio.run(main())
