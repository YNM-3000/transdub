"""Load the channel watchlist config (JSON).

Shape:
{
  "scan_limit": 5,
  "categories": {
    "life-knowledge": {
      "min_trending_views": 100000,
      "channels": [{"id": "UC...", "name": "Zeus"}]
    }
  }
}
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Category, ChannelRef, WatchConfig

DEFAULT_TRENDING_VIEWS = 100_000
DEFAULT_SCAN_LIMIT = 5


def load_config(path: str | Path) -> WatchConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    categories = []
    for name, cat in (data.get("categories") or {}).items():
        channels = tuple(
            ChannelRef(id=ch["id"], name=ch.get("name", ""), category=name)
            for ch in (cat.get("channels") or [])
        )
        categories.append(
            Category(
                name=name,
                min_trending_views=int(
                    cat.get("min_trending_views", DEFAULT_TRENDING_VIEWS)
                ),
                channels=channels,
            )
        )
    return WatchConfig(
        categories=tuple(categories),
        scan_limit=int(data.get("scan_limit", DEFAULT_SCAN_LIMIT)),
    )
