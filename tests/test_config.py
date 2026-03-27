import json

import pytest

from path_app.config import AppConfig, DEFAULT_CONFIG, load_config


def test_load_config_missing_file_creates_and_returns_defaults(tmp_path) -> None:
    config_file = tmp_path / "config.json"
    cfg = load_config(config_file)

    assert config_file.exists(), "missing config.json should be created"
    assert cfg.station == DEFAULT_CONFIG["station"]
    assert cfg.poll_baseline_seconds == DEFAULT_CONFIG["poll_baseline_seconds"]
    assert cfg.show_presumed_trains == DEFAULT_CONFIG["show_presumed_trains"]


def test_load_config_reads_full_file(tmp_path) -> None:
    data = DEFAULT_CONFIG.copy()
    data["station"] = "JSQ"
    data["max_cards"] = 3
    (tmp_path / "config.json").write_text(json.dumps(data))

    cfg = load_config(tmp_path / "config.json")

    assert cfg.station == "JSQ"
    assert cfg.max_cards == 3


def test_load_config_merges_partial_file_with_defaults(tmp_path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"station": "CHR"}))

    cfg = load_config(tmp_path / "config.json")

    assert cfg.station == "CHR"
    assert cfg.poll_baseline_seconds == DEFAULT_CONFIG["poll_baseline_seconds"]
    assert cfg.max_cards == DEFAULT_CONFIG["max_cards"]


def test_load_config_falls_back_on_invalid_json(tmp_path) -> None:
    (tmp_path / "config.json").write_text("{ not valid json }")

    cfg = load_config(tmp_path / "config.json")

    assert cfg.station == DEFAULT_CONFIG["station"]
    assert isinstance(cfg, AppConfig)


def test_load_config_coerces_types(tmp_path) -> None:
    data = DEFAULT_CONFIG.copy()
    data["max_cards"] = "4"
    data["jitter_ratio"] = "0.2"
    data["show_presumed_trains"] = 0
    (tmp_path / "config.json").write_text(json.dumps(data))

    cfg = load_config(tmp_path / "config.json")

    assert cfg.max_cards == 4
    assert cfg.jitter_ratio == pytest.approx(0.2)
    assert cfg.show_presumed_trains is False
