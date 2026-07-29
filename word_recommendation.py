from __future__ import annotations

import hashlib
import json


WORD_CACHE_NAME = "word_cache"
WORD_PROMPT_VERSION = 3
WORD_RECENT_RECOMMENDATION_LIMIT = 14


def word_profile_fingerprint(name: str, birthdate: str) -> str:
    profile_json = json.dumps(
        {
            "name": name,
            "birthdate": birthdate,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(profile_json.encode("utf-8")).hexdigest()


def word_recent_recommendations(
    cached_entry: object,
    profile_fingerprint: str,
) -> list[str]:
    if (
        not isinstance(cached_entry, dict)
        or cached_entry.get("profile_fingerprint") != profile_fingerprint
    ):
        return []

    raw_recent = cached_entry.get("recent_recommendations")
    candidates = raw_recent if isinstance(raw_recent, list) else []
    legacy_answer = cached_entry.get("answer")
    if isinstance(legacy_answer, str):
        candidates = [*candidates, legacy_answer]

    recent: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        answer = candidate.strip()
        if not answer or answer in recent:
            continue
        recent.append(answer)
    return recent[-WORD_RECENT_RECOMMENDATION_LIMIT:]


def append_word_recommendation(
    recent_recommendations: list[str],
    answer: str,
) -> list[str]:
    normalized_answer = answer.strip()
    recent = [
        recommendation
        for recommendation in recent_recommendations
        if recommendation != normalized_answer
    ]
    recent.append(normalized_answer)
    return recent[-WORD_RECENT_RECOMMENDATION_LIMIT:]
