from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    "station": "HOB",
    "poll_seconds": 45,
    "stale_after_seconds": 120,
    "max_cards": 5,
    "font_family": "Inter, Segoe UI, Arial",
}


@dataclass
class AppConfig:
    station: str
    poll_seconds: int
    stale_after_seconds: int
    max_cards: int
    font_family: str


def _merge_with_defaults(raw: Dict[str, Any]) -> Dict[str, Any]:
    merged = DEFAULT_CONFIG.copy()
    merged.update({k: v for k, v in raw.items() if v is not None})
    return merged


def load_config(path: Path | None = None) -> AppConfig:
    """Load config, creating it with defaults if missing."""
    config_path = path or Path("config.json")
    if not config_path.exists():
        config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
        data = DEFAULT_CONFIG
    else:
        try:
            data = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            data = DEFAULT_CONFIG
    merged = _merge_with_defaults(data)
    return AppConfig(
        station=str(merged["station"]),
        poll_seconds=int(merged["poll_seconds"]),
        stale_after_seconds=int(merged["stale_after_seconds"]),
        max_cards=int(merged["max_cards"]),
        font_family=str(merged["font_family"]),
    )


__all__ = ["AppConfig", "DEFAULT_CONFIG", "load_config"]

