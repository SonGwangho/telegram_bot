from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any


FORTUNE_CACHE_NAME = "fortune_cache"
FORTUNE_PROMPT_VERSION = 1
FORTUNE_RECENT_LIMIT = 7
FORTUNE_THEME_COUNT = 2

# (등급, 가중치, 톤 지시문)
# 모델은 이 지시문에 복종한다. 수위 조정이 필요하면 여기만 고친다.
FORTUNE_GRADES: tuple[tuple[str, int, str], ...] = (
    (
        "대길",
        1,
        "오늘은 대놓고 좋은 날이다. 망설이지 말고 밀어붙이라고 단정해서 말한다. "
        "조심하라는 말이나 단서를 달지 않는다.",
    ),
    (
        "길",
        3,
        "오늘은 잘 풀리는 날이다. 무엇이 어떻게 잘 풀리는지 구체적으로 말한다. "
        "걸림돌이나 주의사항은 언급하지 않는다.",
    ),
    (
        "소길",
        4,
        "대체로 괜찮은 날이다. 좋은 흐름을 먼저 말하고, 사소한 주의점은 딱 하나만 덧붙인다.",
    ),
    (
        "평",
        4,
        "특별할 것 없는 밋밋한 날이다. 좋지도 나쁘지도 않다고 솔직하게 말한다. "
        "억지로 좋은 일이나 나쁜 일을 지어내지 않는다.",
    ),
    (
        "흉",
        3,
        "오늘은 안 풀리는 날이다. 무엇이 어떻게 꼬이는지 구체적으로 단정한다. "
        "'그래도 좋은 면이 있다' 같은 무마는 하지 않는다. "
        "능청스러운 농담조를 유지하고, 마지막 한 줄에 그날을 넘길 대처법을 준다.",
    ),
    (
        "대흉",
        1,
        "오늘은 최악이다. 수위를 낮추지 말고 가차없이 나쁘게 쓴다. "
        "얼마나 꼬이는지 과장해서 구체적으로 단정한다. 위로하지 않는다. "
        "다만 문장 전체를 웃기고 능청스러운 농담조로 쓰고, "
        "마지막 한 줄에 그날을 버텨낼 대처법을 준다.",
    ),
)

FORTUNE_THEMES: tuple[str, ...] = (
    "돈 나가는 일",
    "뜻밖의 수입",
    "사람 관계에서 생기는 마찰",
    "오래 못 본 사람과의 연락",
    "일이나 공부의 진척",
    "상사나 선생에게 듣는 말",
    "이동과 약속",
    "오늘 먹는 것",
    "무심코 뱉은 말",
    "물건을 잃어버리거나 되찾는 일",
    "타이밍과 순서",
    "미뤄둔 일",
    "낯선 곳이나 처음 하는 일",
    "기계나 전자기기",
    "잠과 컨디션",
    "충동적으로 내리는 결정",
)

FORTUNE_STYLES: tuple[str, ...] = (
    "담백하고 짧게 끊어 치는 말투",
    "능청스럽게 놀리는 말투",
    "단호하게 못 박는 말투",
    "옛날 점집 무당 같은 예스러운 말투",
    "친한 친구가 툭 던지듯 하는 반말 섞인 말투",
    "뉴스 앵커처럼 건조하게 보도하는 말투",
    "과장 섞어 호들갑 떠는 말투",
    "선문답하듯 툭 던지는 말투",
)

_GRADE_TOTAL_WEIGHT = sum(weight for _, weight, _ in FORTUNE_GRADES)
_GRADE_DIRECTIVES = {name: directive for name, _, directive in FORTUNE_GRADES}


def fortune_profile_fingerprint(name: str, birthdate: str) -> str:
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


def grade_directive(grade: str) -> str:
    """등급명에 해당하는 톤 지시문. 알 수 없는 등급이면 빈 문자열."""

    return _GRADE_DIRECTIVES.get(str(grade).strip(), "")


def roll_fortune(user_id: str, date: str, question: str) -> dict[str, Any]:
    """user_id·날짜·질문으로 그날의 길흉·소재·문체를 결정한다.

    `random` 을 쓰지 않으므로 같은 입력이면 프로세스가 재시작돼도 같은 결과가 나온다.
    """

    seed = "|".join(
        [
            str(user_id).strip(),
            str(date).strip(),
            str(question).strip(),
            f"v{FORTUNE_PROMPT_VERSION}",
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).digest()

    grade = _pick_grade(int.from_bytes(digest[0:4], "big"))
    themes = _pick_themes(int.from_bytes(digest[4:12], "big"))
    style = FORTUNE_STYLES[int.from_bytes(digest[12:16], "big") % len(FORTUNE_STYLES)]

    return {
        "grade": grade,
        "grade_directive": grade_directive(grade),
        "themes": themes,
        "style": style,
    }


def _pick_grade(value: int) -> str:
    position = value % _GRADE_TOTAL_WEIGHT
    for name, weight, _ in FORTUNE_GRADES:
        if position < weight:
            return name
        position -= weight
    return FORTUNE_GRADES[-1][0]


def _pick_themes(value: int) -> list[str]:
    count = min(FORTUNE_THEME_COUNT, len(FORTUNE_THEMES))
    pool = list(FORTUNE_THEMES)
    picked: list[str] = []
    for _ in range(count):
        size = len(pool)
        picked.append(pool.pop(value % size))
        value //= size
    return picked


def normalize_fortune_entry(
    cached_entry: Any,
    *,
    date: str,
    profile_fingerprint: str,
) -> dict[str, Any]:
    """캐시 항목을 현재 스키마로 정규화한다.

    레거시 스키마(`{"YYYY-MM-DD:질문": "답변"}`)도 받아 변환한다.
    날짜가 오늘이 아니거나 프로필·프롬프트 버전이 바뀌었으면 오늘의 답변은 버리고
    최근 답변 목록만 남긴다.
    """

    if not isinstance(cached_entry, dict):
        return _empty_entry(date, profile_fingerprint)

    if _is_legacy_entry(cached_entry):
        answers, recent = _split_legacy_entry(cached_entry, date)
        return {
            "prompt_version": FORTUNE_PROMPT_VERSION,
            "profile_fingerprint": profile_fingerprint,
            "date": date,
            "answers": answers,
            "recent": recent,
        }

    recent = _normalize_answers(cached_entry.get("recent"))
    reusable = (
        cached_entry.get("date") == date
        and cached_entry.get("profile_fingerprint") == profile_fingerprint
        and cached_entry.get("prompt_version") == FORTUNE_PROMPT_VERSION
    )

    answers: dict[str, str] = {}
    if reusable:
        raw_answers = cached_entry.get("answers")
        if isinstance(raw_answers, dict):
            for question, answer in raw_answers.items():
                if isinstance(question, str) and isinstance(answer, str) and answer.strip():
                    answers[question] = answer

    return {
        "prompt_version": FORTUNE_PROMPT_VERSION,
        "profile_fingerprint": profile_fingerprint,
        "date": date,
        "answers": answers,
        "recent": recent,
    }


def append_fortune_answer(recent: Sequence[str], answer: str) -> list[str]:
    normalized_answer = str(answer).strip()
    if not normalized_answer:
        return list(recent)[-FORTUNE_RECENT_LIMIT:]

    updated = [
        item
        for item in _normalize_answers(recent)
        if item != normalized_answer
    ]
    updated.append(normalized_answer)
    return updated[-FORTUNE_RECENT_LIMIT:]


def _empty_entry(date: str, profile_fingerprint: str) -> dict[str, Any]:
    return {
        "prompt_version": FORTUNE_PROMPT_VERSION,
        "profile_fingerprint": profile_fingerprint,
        "date": date,
        "answers": {},
        "recent": [],
    }


def _is_legacy_entry(cached_entry: dict[str, Any]) -> bool:
    if not cached_entry:
        return False
    if not all(isinstance(value, str) for value in cached_entry.values()):
        return False
    return any(
        isinstance(key, str) and ":" in key
        for key in cached_entry
    )


def _split_legacy_entry(
    cached_entry: dict[str, Any],
    date: str,
) -> tuple[dict[str, str], list[str]]:
    answers: dict[str, str] = {}
    dated: list[tuple[str, str]] = []

    for key, value in cached_entry.items():
        if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
            continue
        entry_date, separator, question = key.partition(":")
        if not separator:
            continue
        if entry_date == date:
            answers[question] = value
        dated.append((entry_date, value))

    dated.sort(key=lambda item: item[0])
    recent = _normalize_answers([value for _, value in dated])
    return answers, recent


def _normalize_answers(values: Any) -> list[str]:
    if isinstance(values, str) or not isinstance(values, Sequence):
        return []

    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        answer = value.strip()
        if not answer or answer in normalized:
            continue
        normalized.append(answer)
    return normalized[-FORTUNE_RECENT_LIMIT:]
