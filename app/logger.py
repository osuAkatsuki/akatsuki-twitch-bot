from __future__ import annotations

import logging.config

import yaml


def configure_logging(log_level: str) -> None:
    with open("logging.yaml") as f:
        config = yaml.safe_load(f.read())

    normalized_log_level = log_level.upper()
    config["handlers"]["console"]["level"] = normalized_log_level
    config["root"]["level"] = normalized_log_level
    logging.config.dictConfig(config)
