"""
IBKR Client Portal API — read-only integration.

IBKR Client Portal Gateway must be running locally (typically at https://localhost:5000).
This module talks to that gateway — never directly to IBKR's public APIs.

IMPORTANT: This integration is READ-ONLY. No trading operations are implemented.
Trade execution is explicitly deferred per project design.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

# IBKR Client Portal Gateway ignores SSL cert validation locally
VERIFY_SSL = False


class IBKRClient:
    """Read-only IBKR Client Portal API client."""

    def __init__(self) -> None:
        self._base_url = get_secrets().ibkr_client_portal_url.rstrip("/")
        self._account_id = get_secrets().ibkr_account_id

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            verify=VERIFY_SSL,
            timeout=30,
        )

    async def get_account_summary(self) -> dict[str, Any]:
        """Get account summary (NAV, cash, etc.)."""
        async with self._client() as c:
            r = await c.get(f"/v1/api/portfolio/{self._account_id}/summary")
            r.raise_for_status()
            return r.json()

    async def get_positions(self) -> list[dict[str, Any]]:
        """Get all current positions."""
        async with self._client() as c:
            r = await c.get(f"/v1/api/portfolio/{self._account_id}/positions/0")
            r.raise_for_status()
            return r.json()

    async def get_portfolio_allocation(self) -> dict[str, Any]:
        """Get portfolio allocation by asset class."""
        async with self._client() as c:
            r = await c.get(f"/v1/api/portfolio/{self._account_id}/allocation")
            r.raise_for_status()
            return r.json()

    async def get_market_data(self, conids: list[str]) -> list[dict[str, Any]]:
        """Get market data snapshot for given contract IDs."""
        fields = "55,31,84,86,7295,7296"  # symbol, last, bid, ask, open, close
        conids_str = ",".join(conids)
        async with self._client() as c:
            r = await c.get(
                f"/v1/api/md/snapshot",
                params={"conids": conids_str, "fields": fields},
            )
            r.raise_for_status()
            return r.json()

    async def get_pnl(self) -> dict[str, Any]:
        """Get P&L data."""
        async with self._client() as c:
            r = await c.get(f"/v1/api/iserver/account/pnl/partitioned")
            r.raise_for_status()
            return r.json()

    async def search_contract(self, symbol: str) -> list[dict[str, Any]]:
        """Search for a contract by symbol."""
        async with self._client() as c:
            r = await c.post(
                "/v1/api/iserver/secdef/search",
                json={"symbol": symbol, "secType": "STK"},
            )
            r.raise_for_status()
            return r.json()

    async def is_authenticated(self) -> bool:
        """Check if the IBKR session is authenticated."""
        try:
            async with self._client() as c:
                r = await c.get("/v1/api/iserver/auth/status")
                data = r.json()
                return data.get("authenticated", False)
        except Exception:
            return False

    async def reauthenticate(self) -> bool:
        """Trigger reauthentication (user must approve in IBKR mobile app)."""
        try:
            async with self._client() as c:
                r = await c.post("/v1/api/iserver/reauthenticate")
                return r.status_code == 200
        except Exception:
            return False

    def format_portfolio_summary(
        self,
        positions: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> str:
        """Format portfolio data into a readable Telegram message."""
        lines = ["📊 *Portfolio Summary*\n"]

        # Account metrics
        nav = summary.get("netliquidation", {})
        if nav:
            lines.append(f"💰 Net Liquidation: `${float(nav.get('amount', 0)):,.2f}`")

        cash = summary.get("totalcashvalue", {})
        if cash:
            lines.append(f"💵 Cash: `${float(cash.get('amount', 0)):,.2f}`")

        unrealized = summary.get("unrealizedpnl", {})
        if unrealized:
            amt = float(unrealized.get("amount", 0))
            icon = "🟢" if amt >= 0 else "🔴"
            lines.append(f"{icon} Unrealized P&L: `${amt:,.2f}`")

        lines.append("")

        # Top positions
        if positions:
            lines.append("📈 *Positions*")
            sorted_positions = sorted(
                positions,
                key=lambda p: abs(float(p.get("mktValue", 0))),
                reverse=True,
            )
            for pos in sorted_positions[:10]:
                ticker = pos.get("ticker", pos.get("contractDesc", "?"))
                mkt_val = float(pos.get("mktValue", 0))
                pnl = float(pos.get("unrealizedPnl", 0))
                pct = float(pos.get("pctOfNAV", 0))
                pnl_icon = "🟢" if pnl >= 0 else "🔴"
                lines.append(
                    f"• `{ticker}` — ${mkt_val:,.0f} ({pct:.1f}% NAV) "
                    f"{pnl_icon} ${pnl:+,.0f}"
                )

        return "\n".join(lines)
