from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    "station": "HOB",
    "poll_baseline_seconds": 30,
    "poll_aggressive_seconds": 15,
    "poll_relaxed_seconds": 90,
    "poll_background_seconds": 300,
    "aggressive_threshold_seconds": 300,
    "relaxed_threshold_seconds": 900,
    "jitter_ratio": 0.1,
    "ttl_seconds": 45,
    "ttl_aggressive_seconds": 20,
    "stale_no_change_polls": 3,
    "stale_failure_polls": 3,
    "stale_after_seconds": 120,  # legacy; still used as fallback for UI
    "max_cards": 5,
    "font_family": "Inter, Segoe UI, Arial",
}


@dataclass
class AppConfig:
    station: str
    poll_baseline_seconds: int
    poll_aggressive_seconds: int
    poll_relaxed_seconds: int
    poll_background_seconds: int
    aggressive_threshold_seconds: int
    relaxed_threshold_seconds: int
    jitter_ratio: float
    ttl_seconds: int
    ttl_aggressive_seconds: int
    stale_no_change_polls: int
    stale_failure_polls: int
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
        poll_baseline_seconds=int(merged["poll_baseline_seconds"]),
        poll_aggressive_seconds=int(merged["poll_aggressive_seconds"]),
        poll_relaxed_seconds=int(merged["poll_relaxed_seconds"]),
        poll_background_seconds=int(merged["poll_background_seconds"]),
        aggressive_threshold_seconds=int(merged["aggressive_threshold_seconds"]),
        relaxed_threshold_seconds=int(merged["relaxed_threshold_seconds"]),
        jitter_ratio=float(merged["jitter_ratio"]),
        ttl_seconds=int(merged["ttl_seconds"]),
        ttl_aggressive_seconds=int(merged["ttl_aggressive_seconds"]),
        stale_no_change_polls=int(merged["stale_no_change_polls"]),
        stale_failure_polls=int(merged["stale_failure_polls"]),
        stale_after_seconds=int(merged["stale_after_seconds"]),
        max_cards=int(merged["max_cards"]),
        font_family=str(merged["font_family"]),
    )


__all__ = ["AppConfig", "DEFAULT_CONFIG", "load_config"]
