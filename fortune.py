from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import Any


FORTUNE_CACHE_NAME = "fortune_cache"
FORTUNE_PROMPT_VERSION = 2
FORTUNE_RECENT_LIMIT = 14
FORTUNE_THEME_COUNT = 2
FORTUNE_MAX_ATTEMPTS = 2
FORTUNE_SIMILARITY_THRESHOLD = 0.72

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
    "작은 구매와 가격 비교",
    "빌려주거나 빌린 물건",
    "집 안 정리와 뜻밖의 발견",
    "친구와 주고받는 부탁",
    "가족과 나누는 짧은 대화",
    "새로운 사람과의 첫인상",
    "답장을 보내거나 기다리는 일",
    "약속을 잡거나 취소하는 일",
    "협업에서 맡은 역할",
    "작업을 마무리하고 확인받는 일",
    "실수에 대처하는 순발력",
    "아이디어를 설명하고 설득하는 일",
    "익숙한 길에서 마주치는 변화",
    "취미와 손으로 만드는 것",
    "메모와 기록에서 얻는 단서",
    "오래된 사진이나 물건이 떠올리는 기억",
    "줄을 서거나 차례를 기다리는 일",
    "주변의 소음과 집중력",
    "자투리 시간의 활용",
    "칭찬이나 오해를 받는 순간",
    "고르기 어려운 작은 선택",
    "함께 먹는 식사와 대화",
    "작은 경쟁과 승부욕",
    "마감과 예상 밖의 일정 변경",
    "상대에게 어울리는 작은 선물을 고르는 일",
    "고마움을 말로 표현하는 순간",
    "새로운 취향을 다른 사람과 공유하는 일",
    "부담스러운 관계에서 적당한 거리를 찾는 일",
    "누군가의 비밀을 지켜 주는 일",
    "오래 남은 서운함을 풀어내는 대화",
    "우연히 마주친 지인과의 짧은 만남",
    "함께 있는 사람들의 분위기를 읽는 일",
    "친한 사이에서 서로의 경계를 존중하는 일",
    "호감이나 진심을 표현할 타이밍",
    "불필요한 알림을 줄이는 일",
    "구독이나 자동 결제 내역을 확인하는 일",
    "잊고 있던 쿠폰이나 혜택을 발견하는 일",
    "중고 물건을 거래하며 조건을 맞추는 일",
    "작은 저축 목표를 점검하는 일",
    "가계부에서 예상과 다른 항목을 발견하는 일",
    "구매한 물건을 교환하거나 환불하는 일",
    "외식 비용과 만족도 사이에서 고르는 일",
    "기다리던 택배나 배달을 받는 일",
    "식품의 유통기한과 보관 상태를 확인하는 일",
    "요리에서 새로운 재료 조합을 시도하는 일",
    "카페에서 마음에 드는 자리를 찾는 일",
    "식물이나 작은 화분을 돌보는 일",
    "날씨에 맞는 옷차림을 고르는 일",
    "편안한 신발과 겉모습 사이에서 선택하는 일",
    "외출 전에 문단속과 준비물을 확인하는 일",
    "세탁이나 옷 관리에서 신경 쓰이는 작은 부분",
    "집 안의 사소한 고장이나 불편을 해결하는 일",
    "공용 공간에서 질서와 배려를 챙기는 일",
    "늘 앉던 자리 대신 다른 자리를 택하는 일",
    "대중교통 환승과 연결 시간을 맞추는 일",
    "날씨 때문에 이동 계획을 조정하는 일",
    "처음 방문하는 장소의 길을 찾는 일",
    "행사나 전시에서 뜻밖의 관심사를 발견하는 일",
    "가 보고 싶은 여행지의 정보를 살펴보는 일",
    "사진으로 남기고 싶은 장면을 만나는 일",
    "잠깐 멈춰 주변 풍경을 바라보는 일",
    "길에서 본 안내문이나 간판이 주는 정보",
    "우산이나 물병처럼 작은 준비물이 필요한 순간",
    "낯선 가게에서 새로운 물건을 구경하는 일",
    "발표를 앞두고 긴장을 다루는 일",
    "회의에서 발언할 순서를 잡는 일",
    "모르는 것을 질문하고 배우는 일",
    "시험이나 평가 준비에서 빈틈을 발견하는 일",
    "문서의 오탈자나 작은 누락을 찾아내는 일",
    "파일과 사진을 정리하고 백업하는 일",
    "계정 설정이나 접근 권한을 점검하는 일",
    "처음 써 보는 도구나 기능에 적응하는 일",
    "검색 결과에서 필요한 정보를 골라내는 일",
    "작게 시도한 실험의 결과를 확인하는 일",
    "가볍게 몸을 풀고 자세를 바꾸는 일",
    "짧은 산책에서 기분을 전환하는 일",
    "일 사이에 적당한 휴식 간격을 잡는 일",
    "급한 마음을 가라앉히고 속도를 조절하는 일",
    "책이나 글에서 마음에 남는 구절을 발견하는 일",
    "음악이나 공연에서 새로운 즐거움을 찾는 일",
    "스포츠나 경기 이야기를 함께 나누는 일",
    "대화 중 농담을 건넬 적절한 순간",
    "주변 사람의 작은 어려움을 도와주는 일",
    "남은 재료나 물건을 다른 용도로 활용하는 일",
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
    "동네 어른이 생활 지혜를 들려주는 구수한 말투",
    "스포츠 해설자가 작은 사건을 중계하는 말투",
    "탐정이 단서를 짚어 주는 차분한 말투",
    "일기 한 장처럼 구체적인 장면을 떠올리는 말투",
    "짧은 편지를 보내는 다정하지만 솔직한 말투",
    "장터 상인이 흥정하듯 유쾌하게 풀어내는 말투",
)

FORTUNE_SCENES: tuple[str, ...] = (
    "아침에 하루를 시작하며 준비하는 순간",
    "누군가의 메시지를 읽고 답장을 고르는 순간",
    "점심시간에 잠깐 이야기를 나누는 순간",
    "혼자 조용히 일을 처리하는 순간",
    "서로 다른 의견 중 하나를 선택하는 순간",
    "예상과 다른 작은 변수가 끼어드는 순간",
    "밖으로 나갔다 돌아오는 길의 작은 사건",
    "물건이나 기록을 확인하다 눈에 들어오는 단서",
    "계획보다 조금 빠르거나 늦게 움직이는 순간",
    "평소와 다른 방법을 한 번 시도하는 순간",
    "부탁을 하거나 거절해야 하는 순간",
    "하루를 마무리하며 결과를 확인하는 순간",
)

FORTUNE_STRUCTURES: tuple[str, ...] = (
    "핵심 운세를 먼저 못 박고 두 가지 구체적인 장면으로 풀어낸다",
    "작은 장면으로 시작해 그날의 흐름을 설명하고 행동 하나로 끝낸다",
    "오전과 오후의 흐름을 대비하되 둘 다 지정된 길흉에 맞춘다",
    "주요 소재 두 가지를 서로 다른 짧은 문단으로 풀어낸다",
    "눈에 띌 징조 하나를 들고 그것이 이어지는 결과를 설명한다",
    "짧은 질문을 던진 뒤 스스로 답하며 그날의 흐름을 풀어낸다",
    "오늘의 관전 포인트를 제시한 뒤 구체적인 사건과 결말을 붙인다",
    "평소의 예상과 오늘의 흐름을 비교하고 핵심 행동으로 마친다",
)

FORTUNE_ENDINGS: tuple[str, ...] = (
    "본문의 상황에서 나온 짧고 재치 있는 격언 한 줄로 끝낸다",
    "오늘 바로 할 수 있는 구체적인 행동 한 가지로 끝낸다",
    "본문의 비유를 다시 살린 능청스러운 한 줄로 끝낸다",
    "기억해 둘 짧은 구호 한 줄로 끝낸다",
    "오늘의 핵심 선택을 간결하게 못 박는 문장으로 끝낸다",
    "본문의 작은 장면을 마무리하는 짧은 문장으로 끝낸다",
    "친구에게 툭 건네는 현실적인 조언 한 줄로 끝낸다",
    "오늘의 분위기를 요약하는 뜻밖의 생활 비유로 끝낸다",
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


def roll_fortune(
    user_id: str,
    date: str,
    question: str,
    *,
    recent_rolls: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """user_id·날짜·질문과 최근 조합으로 그날의 길흉·소재·문체를 결정한다.

    `random` 을 쓰지 않으므로 같은 입력이면 프로세스가 재시작돼도 같은 결과가 나온다.
    """

    seed = "|".join(
        [
            str(user_id).strip(),
            str(date).strip(),
            str(question).strip(),
            "v1",
        ]
    )
    # 길흉의 기존 추첨은 유지하고, 표현에 쓰는 조합만 별도로 다양화한다.
    grade_digest = hashlib.sha256(seed.encode("utf-8")).digest()
    digest = hashlib.sha256(f"{seed}|brief-v{FORTUNE_PROMPT_VERSION}".encode("utf-8")).digest()
    recent = _normalize_rolls(recent_rolls)[-3:]

    grade = _pick_grade(int.from_bytes(grade_digest[0:4], "big"))
    themes = _pick_themes(
        int.from_bytes(digest[4:12], "big"),
        excluded={theme for roll in recent for theme in roll["themes"]},
    )

    def choose(options: Sequence[str], field: str, offset: int) -> str:
        excluded = {roll.get(field) for roll in recent}
        pool = [option for option in options if option not in excluded] or list(options)
        return pool[int.from_bytes(digest[offset:offset + 4], "big") % len(pool)]

    return {
        "grade": grade,
        "grade_directive": grade_directive(grade),
        "themes": themes,
        "style": choose(FORTUNE_STYLES, "style", 12),
        "scene": choose(FORTUNE_SCENES, "scene", 16),
        "structure": choose(FORTUNE_STRUCTURES, "structure", 20),
        "ending": choose(FORTUNE_ENDINGS, "ending", 24),
    }


def _pick_grade(value: int) -> str:
    position = value % _GRADE_TOTAL_WEIGHT
    for name, weight, _ in FORTUNE_GRADES:
        if position < weight:
            return name
        position -= weight
    return FORTUNE_GRADES[-1][0]


def _pick_themes(value: int, *, excluded: set[str] | None = None) -> list[str]:
    count = min(FORTUNE_THEME_COUNT, len(FORTUNE_THEMES))
    pool = [theme for theme in FORTUNE_THEMES if theme not in (excluded or set())]
    if len(pool) < count:
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
        answers, recent = _split_legacy_entry(cached_entry)
        return {
            "prompt_version": FORTUNE_PROMPT_VERSION,
            "profile_fingerprint": profile_fingerprint,
            "date": date,
            "answers": answers,
            "recent": recent,
            "recent_rolls": [],
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
        "recent_rolls": _normalize_rolls(cached_entry.get("recent_rolls")),
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


def append_fortune_roll(
    recent_rolls: Sequence[dict[str, Any]],
    roll: dict[str, Any],
    *,
    date: str,
    question: str,
) -> list[dict[str, Any]]:
    updated = [
        item for item in _normalize_rolls(recent_rolls)
        if (item["date"], item["question"]) != (date, question)
    ]
    return _normalize_rolls([*updated, {**roll, "date": date, "question": question}])


def normalize_recent_fortunes(values: Any) -> list[str]:
    return _normalize_answers(values)


def fortune_similarity(answer: str, recent: Sequence[str]) -> float:
    """날짜·이름이 담긴 공통 첫 줄을 제외하고 본문 표현의 반복을 비교한다."""
    def body(text: str) -> str:
        lines = str(text).strip().splitlines()
        if lines and re.match(r"^\d{4}년\s*\d{1,2}월\s*\d{1,2}일.*운세", lines[0]):
            lines = lines[1:]
        return re.sub(r"[^0-9a-z가-힣]+", "", "".join(lines).casefold())[:1000]

    candidate = body(answer)
    if not candidate:
        return 0.0
    candidate_grams = {candidate[i:i + 5] for i in range(max(0, len(candidate) - 4))}
    scores = [0.0]
    for previous in _normalize_answers(recent):
        other = body(previous)
        if not other:
            continue
        sequence_score = SequenceMatcher(None, candidate, other, autojunk=False).ratio()
        other_grams = {other[i:i + 5] for i in range(max(0, len(other) - 4))}
        overlap = len(candidate_grams & other_grams) / max(len(candidate_grams), len(other_grams), 1)
        scores.append(max(sequence_score, overlap))
    return max(scores)


def _normalize_rolls(values: Any) -> list[dict[str, Any]]:
    if isinstance(values, str) or not isinstance(values, Sequence):
        return []
    result = []
    for value in values:
        if not isinstance(value, dict):
            continue
        raw_themes = value.get("themes")
        themes = [theme for theme in raw_themes if isinstance(theme, str) and theme in FORTUNE_THEMES] if isinstance(raw_themes, list) else []
        if not themes:
            continue
        item = {"themes": themes[:FORTUNE_THEME_COUNT]}
        for field in ("date", "question", "style", "scene", "structure", "ending"):
            item[field] = str(value.get(field) or "")
        result.append(item)
    return result[-FORTUNE_RECENT_LIMIT:]


def _empty_entry(date: str, profile_fingerprint: str) -> dict[str, Any]:
    return {
        "prompt_version": FORTUNE_PROMPT_VERSION,
        "profile_fingerprint": profile_fingerprint,
        "date": date,
        "answers": {},
        "recent": [],
        "recent_rolls": [],
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


def _split_legacy_entry(cached_entry: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    answers: dict[str, str] = {}
    dated: list[tuple[str, str]] = []

    for key, value in cached_entry.items():
        if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
            continue
        entry_date, separator, _ = key.partition(":")
        if not separator:
            continue
        # 레거시에는 프로필과 프롬프트 버전이 없어 오늘의 답변으로 재사용하지 않는다.
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
