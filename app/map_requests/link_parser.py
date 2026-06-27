from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlparse

from app.models import BeatmapLink


URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,!?:;]"
OSU_HOSTS = {"osu.ppy.sh", "www.osu.ppy.sh"}
AKATSUKI_HOSTS = {"akatsuki.gg", "www.akatsuki.gg"}
BEATMAP_FRAGMENT_RE = re.compile(r"(?:^|/)(?:osu|taiko|fruits|mania)/(?P<id>\d+)$")


def extract_beatmap_links(text: str) -> list[BeatmapLink]:
    links: list[BeatmapLink] = []
    seen_ids: set[int] = set()

    for raw_url in _candidate_urls(text):
        beatmap_id = _extract_beatmap_id(raw_url)
        if beatmap_id is None or beatmap_id in seen_ids:
            continue

        seen_ids.add(beatmap_id)
        links.append(
            BeatmapLink(
                beatmap_id=beatmap_id,
                url=f"https://osu.ppy.sh/b/{beatmap_id}",
            ),
        )

    return links


def _candidate_urls(text: str) -> Iterable[str]:
    for match in URL_RE.finditer(text):
        yield match.group(0).rstrip(TRAILING_PUNCTUATION)


def _extract_beatmap_id(raw_url: str) -> int | None:
    parsed = urlparse(raw_url)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host not in OSU_HOSTS and host not in AKATSUKI_HOSTS:
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"b", "beatmaps"}:
        return _parse_positive_int(parts[1])

    if host in OSU_HOSTS and len(parts) >= 2 and parts[0] == "beatmapsets":
        fragment_match = BEATMAP_FRAGMENT_RE.search(parsed.fragment)
        if fragment_match is not None:
            return _parse_positive_int(fragment_match.group("id"))

    return None


def _parse_positive_int(value: str) -> int | None:
    if not value.isdigit():
        return None

    parsed = int(value)
    return parsed if parsed > 0 else None
