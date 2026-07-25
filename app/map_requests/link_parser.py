from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlparse

from app.models import BeatmapLink


URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,!?:;]\"'"
OSU_HOSTS = {"osu.ppy.sh", "www.osu.ppy.sh"}
AKATSUKI_HOSTS = {
    "akatsuki.gg",
    "www.akatsuki.gg",
    "osu.akatsuki.gg",
    "www.osu.akatsuki.gg",
}
BEATMAP_FRAGMENT_RE = re.compile(
    r"^(?:(?:osu|taiko|fruits|mania)/|/(?:osu|taiko|fruits|mania)/|/)(?P<id>\d+)$",
)


def extract_beatmap_links(text: str) -> list[BeatmapLink]:
    links: list[BeatmapLink] = []
    seen_ids: set[int] = set()

    for raw_url in _candidate_urls(text):
        beatmap_link = _extract_beatmap_link(raw_url)
        if beatmap_link is None or beatmap_link.beatmap_id in seen_ids:
            continue

        seen_ids.add(beatmap_link.beatmap_id)
        links.append(beatmap_link)

    return links


def _candidate_urls(text: str) -> Iterable[str]:
    for match in URL_RE.finditer(text):
        yield match.group(0).rstrip(TRAILING_PUNCTUATION)


def _extract_beatmap_link(raw_url: str) -> BeatmapLink | None:
    parsed = urlparse(raw_url)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host not in OSU_HOSTS and host not in AKATSUKI_HOSTS:
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"b", "beatmaps"}:
        beatmap_id = _parse_positive_int(parts[1])
        if beatmap_id is None:
            return None

        return BeatmapLink(
            beatmap_id=beatmap_id,
            url=f"https://akatsuki.gg/b/{beatmap_id}",
        )

    if len(parts) >= 4 and parts[0] == "beatmapsets" and parts[2] == "beatmaps":
        beatmapset_id = _parse_positive_int(parts[1])
        beatmap_id = _parse_positive_int(parts[3])
        if beatmapset_id is None or beatmap_id is None:
            return None

        return _beatmapset_link(beatmapset_id, beatmap_id)

    if len(parts) >= 2 and parts[0] == "beatmapsets":
        beatmapset_id = _parse_positive_int(parts[1])
        if beatmapset_id is None:
            return None

        fragment_match = BEATMAP_FRAGMENT_RE.search(parsed.fragment)
        if fragment_match is not None:
            beatmap_id = _parse_positive_int(fragment_match.group("id"))
            if beatmap_id is None:
                return None

            return _beatmapset_link(beatmapset_id, beatmap_id)

    return None


def _beatmapset_link(beatmapset_id: int, beatmap_id: int) -> BeatmapLink:
    return BeatmapLink(
        beatmap_id=beatmap_id,
        beatmapset_id=beatmapset_id,
        url=f"https://osu.akatsuki.gg/beatmapsets/{beatmapset_id}#/{beatmap_id}",
    )


def _parse_positive_int(value: str) -> int | None:
    if not value.isdigit():
        return None

    parsed = int(value)
    return parsed if parsed > 0 else None
