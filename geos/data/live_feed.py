"""Live market-data ingestion with disk cache + graceful fallback.

Pulls real spot prices (Brent, WTI, natural gas, USD/INR) from a free, no-key
public source. Resilience is the whole point of the demo, so the fetcher is
defensive by design:

    live fetch  →  on failure: last cached value (within TTL or stale)
                →  on cold cache: documented config baseline

Every response is tagged with ``source`` = ``live`` | ``cache`` | ``fallback``
and an ``as_of`` timestamp, so the command center can show provenance honestly.
This turns the system from "synthetic" into "ingests live signals" while
guaranteeing the demo never stalls on a flaky network.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from geos import config

# Yahoo Finance chart endpoint (public, no key). Symbols:
#   BZ=F Brent · CL=F WTI · NG=F Henry Hub gas · INR=X USD/INR
SYMBOLS = {
    "brent": "BZ=F",
    "wti": "CL=F",
    "natgas": "NG=F",
    "usdinr": "INR=X",
}
_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"
_CACHE = Path(config.__file__).resolve().parent.parent / "data_cache" / "prices.json"
_TTL_SECONDS = 900  # 15 minutes


@dataclass
class MarketSnapshot:
    prices: Dict[str, float]
    changes_pct: Dict[str, float] = field(default_factory=dict)
    source: str = "fallback"           # live | cache | fallback
    as_of: float = 0.0
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "prices": {k: round(v, 2) for k, v in self.prices.items()},
            "changes_pct": {k: round(v, 2) for k, v in self.changes_pct.items()},
            "source": self.source,
            "as_of": self.as_of,
            "as_of_iso": (time.strftime("%Y-%m-%d %H:%M:%S UTC",
                                        time.gmtime(self.as_of)) if self.as_of else ""),
            "brent": round(self.prices.get("brent", config.BASELINE_BRENT_USD), 2),
            "note": self.note,
        }


def _fetch_symbol(symbol: str, timeout: float = 6.0) -> Optional[Dict[str, float]]:
    url = _BASE + symbol
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    meta = data["chart"]["result"][0]["meta"]
    price = float(meta["regularMarketPrice"])
    prev = float(meta.get("chartPreviousClose", price) or price)
    change = ((price - prev) / prev * 100) if prev else 0.0
    return {"price": price, "change_pct": change}


def _read_cache() -> Optional[MarketSnapshot]:
    if not _CACHE.exists():
        return None
    try:
        raw = json.loads(_CACHE.read_text())
        return MarketSnapshot(
            prices=raw["prices"], changes_pct=raw.get("changes_pct", {}),
            source="cache", as_of=raw.get("as_of", 0.0),
            note="served from disk cache (live fetch unavailable)",
        )
    except Exception:
        return None


def _write_cache(snap: MarketSnapshot) -> None:
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps({
            "prices": snap.prices, "changes_pct": snap.changes_pct,
            "as_of": snap.as_of,
        }))
    except Exception:
        pass


def _fallback() -> MarketSnapshot:
    return MarketSnapshot(
        prices={"brent": config.BASELINE_BRENT_USD, "wti": config.BASELINE_BRENT_USD - 4,
                "natgas": 3.0, "usdinr": 83.0},
        changes_pct={k: 0.0 for k in SYMBOLS},
        source="fallback",
        as_of=time.time(),
        note="documented baseline (no live data / cold cache)",
    )


class LiveFeed:
    """Cached, fault-tolerant market data provider."""

    def __init__(self, ttl: int = _TTL_SECONDS) -> None:
        self.ttl = ttl
        self._mem: Optional[MarketSnapshot] = None

    def get(self, force: bool = False) -> MarketSnapshot:
        # in-memory hot cache
        if (not force and self._mem and self._mem.source == "live"
                and time.time() - self._mem.as_of < self.ttl):
            return self._mem

        prices, changes = {}, {}
        ok = True
        for name, sym in SYMBOLS.items():
            try:
                r = _fetch_symbol(sym)
                prices[name] = r["price"]
                changes[name] = r["change_pct"]
            except Exception:
                ok = False
                break

        if ok and "brent" in prices:
            snap = MarketSnapshot(prices=prices, changes_pct=changes,
                                  source="live", as_of=time.time(),
                                  note="live market data (Yahoo Finance)")
            self._mem = snap
            _write_cache(snap)
            return snap

        # live failed → cache → fallback
        cached = _read_cache()
        if cached:
            self._mem = cached
            return cached
        return _fallback()

    def live_brent(self) -> float:
        """Brent price to use as the dynamic causal baseline."""
        return self.get().prices.get("brent", config.BASELINE_BRENT_USD)


# module-level singleton
_FEED: Optional[LiveFeed] = None


def get_feed() -> LiveFeed:
    global _FEED
    if _FEED is None:
        _FEED = LiveFeed()
    return _FEED
