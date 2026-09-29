"""우버 진행도 페이지의 조회, 파싱, 짧은 캐시를 담당한다."""

import asyncio

import requests
from bs4 import BeautifulSoup

from lookup_cache import AsyncTTLCache


UBER_TRACKER_URL = "https://diablo2.io/dclonetracker.php"
UBER_REGION_NAMES = {
    "Europe": "유럽",
    "Americas": "미국",
    "Asia": "한국",
}
UBER_MODE_TITLES = (
    ("래더", "RotW Softcore Ladder"),
    ("스탠", "RotW Softcore Non-Ladder"),
)
UBER_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
}
Progress = list[tuple[str, list[tuple[str, str, str]]]]
_progress_cache: AsyncTTLCache[Progress] = AsyncTTLCache(30, max_entries=1)


async def get_progress() -> Progress:
    return await _progress_cache.get(
        "progress", lambda: asyncio.to_thread(fetch_uber_progress)
    )


def fetch_uber_progress() -> Progress:
    with requests.get(
        UBER_TRACKER_URL, headers=UBER_REQUEST_HEADERS, timeout=10
    ) as response:
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

    member_tables = {}
    for card in soup.select(".z-dclone-table-card"):
        heading = card.select_one("h1")
        table = card.select_one("table#memberlist")
        if heading and table:
            member_tables[heading.get_text(" ", strip=True)] = table

    progress_by_mode = []
    for mode_name, table_title in UBER_MODE_TITLES:
        table = member_tables.get(table_title)
        if table is None:
            raise ValueError(f"{mode_name} 진행도 테이블을 찾지 못했습니다.")

        progress_values = []
        for row in table.select("tbody tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 3:
                continue
            code = cells[0].find("code")
            region_text = cells[1].get_text(" ", strip=True)
            last_updated = cells[2].get_text(" ", strip=True)
            region_name = next(
                (
                    korean_name
                    for region_key, korean_name in UBER_REGION_NAMES.items()
                    if region_key in region_text
                ),
                None,
            )
            if code and region_name and last_updated:
                progress_values.append(
                    (region_name, code.get_text(strip=True), last_updated)
                )

        found_regions = {region for region, _, _ in progress_values}
        if found_regions != set(UBER_REGION_NAMES.values()):
            raise ValueError(f"{mode_name} 우버 진행도 3개를 모두 찾지 못했습니다.")
        progress_by_mode.append((mode_name, progress_values))

    return progress_by_mode
