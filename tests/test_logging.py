from __future__ import annotations

import json
import logging

from app.logger import configure_logging


def test_json_logging_includes_extra_fields(capsys) -> None:
    configure_logging("INFO")

    logging.getLogger("app.test").info(
        "Structured event.",
        extra={"channel": "fallenbtw_osu", "beatmap_id": 75},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["message"] == "Structured event."
    assert payload["channel"] == "fallenbtw_osu"
    assert payload["beatmap_id"] == 75
