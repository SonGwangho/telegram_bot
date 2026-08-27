from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import secrets
from typing import Any

import storage


ADJUSTMENT_STORAGE_NAME = "adjustments"
MIN_PARTICIPANTS = 2
MAX_PARTICIPANTS = 50
MAX_EXACT_PARTICIPANTS = 12
MAX_ROOM_NAME_LENGTH = 40
MAX_MEMBER_NAME_LENGTH = 30
MAX_MEMO_LENGTH = 100
MAX_AMOUNT = 999_999_999_999
SETTLEMENT_UNIT = 100
ANONYMOUS_MEMBER_PREFIX = "나머지 참여자 "


class AdjustmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemberSettlement:
    name: str
    paid: int
    share: int
    is_anonymous: bool = False


@dataclass(frozen=True)
class ExpenseEntry:
    member_name: str
    amount: int
    memo: str
    code: str = ""


@dataclass(frozen=True)
class Transfer:
    sender: str
    receiver: str
    amount: int


@dataclass(frozen=True)
class SettlementResult:
    room_name: str
    participant_count: int
    total_amount: int
    base_share: int
    rounding_remainder: int
    anonymous_count: int
    members: tuple[MemberSettlement, ...]
    entries: tuple[ExpenseEntry, ...]
    transfers: tuple[Transfer, ...]
    is_exact_minimum: bool


@dataclass(frozen=True)
class RoomDetails:
    room_name: str
    participant_count: int
    registered_count: int
    total_amount: int
    entries: tuple[ExpenseEntry, ...]


def create_room(
    chat_id: int | str,
    room_name: str,
    participant_count: int,
    *,
    created_by: int | str | None = None,
) -> None:
    room_name = _validate_name(room_name, "모임명", MAX_ROOM_NAME_LENGTH)
    if not MIN_PARTICIPANTS <= participant_count <= MAX_PARTICIPANTS:
        raise AdjustmentError(
            f"인원수는 {MIN_PARTICIPANTS}명부터 {MAX_PARTICIPANTS}명까지 가능합니다."
        )

    data = _load_data()
    rooms = _get_rooms(data, chat_id, create=True)
    if room_name in rooms:
        raise AdjustmentError(f"'{room_name}' 정산이 이미 있습니다.")

    rooms[room_name] = {
        "participant_count": participant_count,
        "members": {},
        "entries": [],
        "created_by": str(created_by) if created_by is not None else None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_data(data)


def add_expense(
    chat_id: int | str,
    room_name: str,
    member_name: str,
    amount: int,
    memo: str = "",
) -> tuple[str, int, int, int, int]:
    room_name = _validate_name(room_name, "모임명", MAX_ROOM_NAME_LENGTH)
    member_name = _validate_name(member_name, "이름", MAX_MEMBER_NAME_LENGTH)
    if amount < 0 or amount > MAX_AMOUNT:
        raise AdjustmentError(f"금액은 0원부터 {MAX_AMOUNT:,}원까지 입력해 주세요.")
    memo = memo.strip()
    if len(memo) > MAX_MEMO_LENGTH:
        raise AdjustmentError(f"메모는 {MAX_MEMO_LENGTH}자 이내로 입력해 주세요.")

    data = _load_data()
    rooms = _get_rooms(data, chat_id)
    room = rooms.get(room_name)
    if not isinstance(room, dict):
        raise AdjustmentError(f"'{room_name}' 정산을 찾을 수 없습니다.")

    participant_count = _room_participant_count(room)
    members = _room_members(room)
    entries = _room_entries(room, members, migrate=True)
    if member_name not in members and len(members) >= participant_count:
        raise AdjustmentError(
            f"'{room_name}' 정산은 이미 {participant_count}명이 모두 등록되었습니다."
        )

    member = members.setdefault(member_name, {"paid": 0})
    previous_paid = _non_negative_int(member.get("paid"), "저장된 결제 금액")
    new_paid = previous_paid + amount
    if new_paid > MAX_AMOUNT:
        raise AdjustmentError(f"한 사람의 누적 금액은 {MAX_AMOUNT:,}원을 넘을 수 없습니다.")

    member["paid"] = new_paid
    entry_code = _generate_entry_code(entries)
    entries.append(
        {
            "code": entry_code,
            "name": member_name,
            "amount": amount,
            "memo": memo,
        }
    )
    _save_data(data)

    total_amount = sum(
        _non_negative_int(value.get("paid"), "저장된 결제 금액")
        for value in members.values()
        if isinstance(value, dict)
    )
    return entry_code, new_paid, len(members), participant_count, total_amount


def get_room_details(
    chat_id: int | str,
    room_name: str,
) -> RoomDetails:
    room_name = _validate_name(room_name, "모임명", MAX_ROOM_NAME_LENGTH)
    data = _load_data()
    rooms = _get_rooms(data, chat_id)
    room = rooms.get(room_name)
    if not isinstance(room, dict):
        raise AdjustmentError(f"'{room_name}' 정산을 찾을 수 없습니다.")

    participant_count = _room_participant_count(room)
    members = _room_members(room)
    raw_entries = _room_entries(room, members, migrate=True)
    if not isinstance(raw_entries, list):
        raise AdjustmentError("저장된 결제 내역이 올바르지 않습니다.")
    entries = _parse_expense_entries(raw_entries)

    total_amount = sum(
        _non_negative_int(value.get("paid"), "저장된 결제 금액")
        for value in members.values()
        if isinstance(value, dict)
    )
    if sum(entry.amount for entry in entries) != total_amount:
        raise AdjustmentError("저장된 결제 내역의 합계가 맞지 않습니다.")
    _save_data(data)

    return RoomDetails(
        room_name=room_name,
        participant_count=participant_count,
        registered_count=len(members),
        total_amount=total_amount,
        entries=entries,
    )


def remove_expense(
    chat_id: int | str,
    room_name: str,
    entry_code: str,
) -> tuple[ExpenseEntry, int, int, int]:
    room_name = _validate_name(room_name, "모임명", MAX_ROOM_NAME_LENGTH)
    if len(entry_code) != 4 or not entry_code.isdecimal():
        raise AdjustmentError("제거할 내역 코드는 4자리 숫자로 입력해 주세요.")

    data = _load_data()
    rooms = _get_rooms(data, chat_id)
    room = rooms.get(room_name)
    if not isinstance(room, dict):
        raise AdjustmentError(f"'{room_name}' 정산을 찾을 수 없습니다.")

    participant_count = _room_participant_count(room)
    members = _room_members(room)
    raw_entries = _room_entries(room, members, migrate=True)
    if not isinstance(raw_entries, list):
        raise AdjustmentError("저장된 결제 내역이 올바르지 않습니다.")

    remove_index = next(
        (
            index
            for index, raw_entry in enumerate(raw_entries)
            if isinstance(raw_entry, dict) and raw_entry.get("code") == entry_code
        ),
        None,
    )
    if remove_index is None:
        raise AdjustmentError(f"'{entry_code}' 내역을 찾을 수 없습니다.")

    removed = _parse_expense_entries([raw_entries.pop(remove_index)])[0]
    remaining_entries = _parse_expense_entries(raw_entries)
    rebuilt_members: dict[str, dict[str, int]] = {}
    for entry in remaining_entries:
        member = rebuilt_members.setdefault(entry.member_name, {"paid": 0})
        member["paid"] += entry.amount
    room["members"] = rebuilt_members
    _save_data(data)

    total_amount = sum(entry.amount for entry in remaining_entries)
    return removed, len(rebuilt_members), participant_count, total_amount


def calculate_settlement(
    chat_id: int | str,
    room_name: str,
) -> SettlementResult:
    room_name = _validate_name(room_name, "모임명", MAX_ROOM_NAME_LENGTH)
    data = _load_data()
    rooms = _get_rooms(data, chat_id)
    room = rooms.get(room_name)
    if not isinstance(room, dict):
        raise AdjustmentError(f"'{room_name}' 정산을 찾을 수 없습니다.")

    participant_count = _room_participant_count(room)
    stored_members = _room_members(room)
    expense_entries = _room_entries(room, stored_members)
    paid_by_name = {
        name: _non_negative_int(value.get("paid"), "저장된 결제 금액")
        for name, value in stored_members.items()
        if isinstance(name, str) and isinstance(value, dict)
    }
    if len(paid_by_name) != len(stored_members):
        raise AdjustmentError("저장된 참여자 정보가 올바르지 않습니다.")
    if len(paid_by_name) > participant_count:
        raise AdjustmentError("등록된 결제자가 정산 인원수보다 많습니다.")
    entry_totals: dict[str, int] = {}
    for entry in expense_entries:
        entry_totals[entry.member_name] = (
            entry_totals.get(entry.member_name, 0) + entry.amount
        )
    if entry_totals != paid_by_name:
        raise AdjustmentError("저장된 결제 내역의 합계가 맞지 않습니다.")

    anonymous_count = participant_count - len(paid_by_name)
    anonymous_names: list[str] = []
    for index in range(1, anonymous_count + 1):
        anonymous_name = f"{ANONYMOUS_MEMBER_PREFIX}{index}"
        while anonymous_name in paid_by_name:
            anonymous_name += "_"
        anonymous_names.append(anonymous_name)

    all_paid_by_name = {
        **paid_by_name,
        **{name: 0 for name in anonymous_names},
    }

    total_amount = sum(all_paid_by_name.values())
    exact_base_share, exact_remainder = divmod(total_amount, participant_count)
    base_share = (exact_base_share // SETTLEMENT_UNIT) * SETTLEMENT_UNIT
    rounding_remainder = total_amount - (base_share * participant_count)

    # 나누어떨어지지 않는 1원은 결제액이 큰 사람부터 부담한다.
    # 같은 금액이면 먼저 등록된 사람을 우선해 결과가 항상 같도록 한다.
    registration_order = {
        name: index for index, name in enumerate(all_paid_by_name)
    }
    extra_share_members = set(
        sorted(
            all_paid_by_name,
            key=lambda name: (-all_paid_by_name[name], registration_order[name]),
        )[:exact_remainder]
    )

    member_results = tuple(
        MemberSettlement(
            name=name,
            paid=paid,
            share=exact_base_share + (1 if name in extra_share_members else 0),
            is_anonymous=name in anonymous_names,
        )
        for name, paid in all_paid_by_name.items()
    )
    balances = {
        member.name: member.paid - member.share
        for member in member_results
        if member.paid != member.share
    }
    balances = _round_transfer_balances(balances, SETTLEMENT_UNIT)

    if len(balances) <= MAX_EXACT_PARTICIPANTS:
        transfers = _calculate_exact_transfers(balances)
        is_exact_minimum = True
    else:
        transfers = _calculate_greedy_transfers(balances)
        is_exact_minimum = False

    return SettlementResult(
        room_name=room_name,
        participant_count=participant_count,
        total_amount=total_amount,
        base_share=base_share,
        rounding_remainder=rounding_remainder,
        anonymous_count=anonymous_count,
        members=member_results,
        entries=expense_entries,
        transfers=transfers,
        is_exact_minimum=is_exact_minimum,
    )


def delete_room(chat_id: int | str, room_name: str) -> None:
    room_name = _validate_name(room_name, "모임명", MAX_ROOM_NAME_LENGTH)
    data = _load_data()
    chat_key = str(chat_id)
    rooms = _get_rooms(data, chat_id)
    if room_name not in rooms:
        raise AdjustmentError(f"'{room_name}' 정산을 찾을 수 없습니다.")

    del rooms[room_name]
    chats = data.get("chats")
    if isinstance(chats, dict) and not rooms:
        chats.pop(chat_key, None)
    _save_data(data)


def format_settlement(result: SettlementResult) -> str:
    lines = [
        f"[{result.room_name}] 정산 마감",
        "",
        "[내역]",
    ]
    if result.entries:
        for entry in result.entries:
            memo_suffix = f" {entry.memo}" if entry.memo else ""
            lines.append(
                f"{entry.member_name} {entry.amount:,}원{memo_suffix}"
            )
    else:
        lines.append("내역 없음")

    lines.extend(
        [
            "",
            f"총액: {result.total_amount:,}원",
            (
                f"인원: {result.participant_count}명 - "
                f"1인 정산 기준: {result.base_share:,}원 (100원 미만 절사)"
            ),
        ]
    )
    if result.rounding_remainder:
        lines.append(
            f"우수리 합계: {result.rounding_remainder:,}원 (결제자 부담)"
        )

    lines.extend(["", "송금 방법"])
    if result.transfers:
        anonymous_transfers: dict[str, list[Transfer]] = {}
        for transfer in result.transfers:
            if transfer.sender.startswith(ANONYMOUS_MEMBER_PREFIX):
                anonymous_transfers.setdefault(transfer.sender, []).append(transfer)
            else:
                lines.append(
                    f"- {transfer.sender} → {transfer.receiver}: {transfer.amount:,}원"
                )

        for sender in sorted(
            anonymous_transfers,
            key=_anonymous_member_number,
        ):
            destinations = " + ".join(
                f"{transfer.receiver} {transfer.amount:,}원"
                for transfer in anonymous_transfers[sender]
            )
            lines.append(
                f"- 인원 {_anonymous_member_number(sender)} → {destinations}"
            )
        minimum_label = "최소" if result.is_exact_minimum else "정리된"
        lines.append(f"총 {len(result.transfers)}회 · {minimum_label} 송금 경로")
    else:
        lines.append("- 서로 송금할 금액이 없습니다.")

    return "\n".join(lines)


def format_room_details(details: RoomDetails) -> str:
    lines = [f"[{details.room_name} 내역]"]
    if details.entries:
        for entry in details.entries:
            memo_suffix = f" {entry.memo}" if entry.memo else ""
            lines.append(
                f"[{entry.code}] {entry.member_name} {entry.amount:,}원{memo_suffix}"
            )
    else:
        lines.append("내역 없음")

    lines.extend(
        [
            "",
            f"총액: {details.total_amount:,}원",
            f"결제자: {details.registered_count}/{details.participant_count}명",
        ]
    )
    return "\n".join(lines)


def _anonymous_member_number(name: str) -> int:
    suffix = name.removeprefix(ANONYMOUS_MEMBER_PREFIX).rstrip("_")
    try:
        return int(suffix)
    except ValueError:
        return MAX_PARTICIPANTS + 1


def _room_entries(
    room: dict[str, Any],
    members: dict[str, Any],
    *,
    migrate: bool = False,
) -> tuple[ExpenseEntry, ...] | list[dict[str, Any]]:
    raw_entries = room.get("entries")
    if raw_entries is None:
        legacy_entries = [
            {
                "name": name,
                "amount": _non_negative_int(value.get("paid"), "저장된 결제 금액"),
                "memo": "",
            }
            for name, value in members.items()
            if isinstance(name, str) and isinstance(value, dict)
        ]
        if migrate:
            room["entries"] = legacy_entries
            return legacy_entries
        raw_entries = legacy_entries

    if not isinstance(raw_entries, list):
        raise AdjustmentError("저장된 결제 내역이 올바르지 않습니다.")
    if migrate:
        _ensure_entry_codes(raw_entries)
        # 추가 또는 조회 전에 기존 내역도 검증한다.
        _parse_expense_entries(raw_entries)
        return raw_entries
    return _parse_expense_entries(raw_entries)


def _parse_expense_entries(raw_entries: list[Any]) -> tuple[ExpenseEntry, ...]:
    entries: list[ExpenseEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise AdjustmentError("저장된 결제 내역이 올바르지 않습니다.")
        name = raw_entry.get("name")
        memo = raw_entry.get("memo", "")
        code = raw_entry.get("code", "")
        if not isinstance(name, str) or not name.strip():
            raise AdjustmentError("저장된 결제자 이름이 올바르지 않습니다.")
        if not isinstance(memo, str) or len(memo) > MAX_MEMO_LENGTH:
            raise AdjustmentError("저장된 결제 메모가 올바르지 않습니다.")
        if code != "" and (
            not isinstance(code, str)
            or len(code) != 4
            or not code.isdecimal()
        ):
            raise AdjustmentError("저장된 결제 코드가 올바르지 않습니다.")
        entries.append(
            ExpenseEntry(
                member_name=name,
                amount=_non_negative_int(
                    raw_entry.get("amount"),
                    "저장된 결제 금액",
                ),
                memo=memo,
                code=code,
            )
        )
    return tuple(entries)


def _ensure_entry_codes(raw_entries: list[Any]) -> None:
    used_codes: set[str] = set()
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise AdjustmentError("저장된 결제 내역이 올바르지 않습니다.")
        code = raw_entry.get("code")
        if (
            not isinstance(code, str)
            or len(code) != 4
            or not code.isdecimal()
            or code in used_codes
        ):
            code = _generate_entry_code(raw_entries, used_codes=used_codes)
            raw_entry["code"] = code
        used_codes.add(code)


def _generate_entry_code(
    raw_entries: list[Any],
    *,
    used_codes: set[str] | None = None,
) -> str:
    if used_codes is None:
        used_codes = {
            str(raw_entry.get("code"))
            for raw_entry in raw_entries
            if isinstance(raw_entry, dict)
            and isinstance(raw_entry.get("code"), str)
            and len(str(raw_entry.get("code"))) == 4
            and str(raw_entry.get("code")).isdecimal()
        }
    if len(used_codes) >= 9_000:
        raise AdjustmentError("정산 내역이 너무 많아 4자리 코드를 만들 수 없습니다.")

    for _ in range(100):
        code = f"{secrets.randbelow(9_000) + 1_000:04d}"
        if code not in used_codes:
            return code
    for number in range(1_000, 10_000):
        code = f"{number:04d}"
        if code not in used_codes:
            return code
    raise AdjustmentError("사용 가능한 4자리 내역 코드가 없습니다.")


def _round_transfer_balances(
    balances: dict[str, int],
    unit: int,
) -> dict[str, int]:
    if unit <= 0:
        raise AdjustmentError("정산 절사 단위가 올바르지 않습니다.")

    rounded_debts = {
        name: ((-balance) // unit) * unit
        for name, balance in balances.items()
        if balance < 0
    }
    target_total = sum(rounded_debts.values())
    if target_total == 0:
        return {}

    exact_credits = {
        name: balance
        for name, balance in balances.items()
        if balance > 0
    }
    rounded_credits = {
        name: (balance // unit) * unit
        for name, balance in exact_credits.items()
    }
    difference = target_total - sum(rounded_credits.values())

    if difference > 0:
        credit_order = sorted(
            exact_credits,
            key=lambda name: (
                -(exact_credits[name] % unit),
                -exact_credits[name],
                name,
            ),
        )
        units_to_add = difference // unit
        for index in range(units_to_add):
            name = credit_order[index % len(credit_order)]
            rounded_credits[name] += unit
    elif difference < 0:
        units_to_remove = (-difference) // unit
        while units_to_remove:
            credit_order = sorted(
                (
                    name
                    for name, amount in rounded_credits.items()
                    if amount >= unit
                ),
                key=lambda name: (-rounded_credits[name], name),
            )
            if not credit_order:
                raise AdjustmentError("100원 단위 송금액을 계산할 수 없습니다.")
            for name in credit_order:
                rounded_credits[name] -= unit
                units_to_remove -= 1
                if units_to_remove == 0:
                    break

    rounded_balances = {
        name: -amount
        for name, amount in rounded_debts.items()
        if amount
    }
    rounded_balances.update(
        {
            name: amount
            for name, amount in rounded_credits.items()
            if amount
        }
    )
    if sum(rounded_balances.values()) != 0:
        raise AdjustmentError("100원 단위 송금액의 합계가 맞지 않습니다.")
    return rounded_balances


def _calculate_exact_transfers(
    balances: dict[str, int],
) -> tuple[Transfer, ...]:
    names = tuple(balances)
    initial_state = tuple(balances[name] for name in names)
    if not initial_state:
        return ()

    @lru_cache(maxsize=None)
    def solve(state: tuple[int, ...]) -> tuple[tuple[int, int], ...]:
        start = next((index for index, value in enumerate(state) if value), -1)
        if start == -1:
            return ()

        current = state[start]
        best: tuple[tuple[int, int], ...] | None = None
        tried_balances: set[int] = set()

        for other_index in range(start + 1, len(state)):
            other = state[other_index]
            if current * other >= 0 or other in tried_balances:
                continue
            tried_balances.add(other)

            next_state = list(state)
            next_state[start] = 0
            next_state[other_index] += current
            candidate = ((start, other_index),) + solve(tuple(next_state))
            if best is None or len(candidate) < len(best):
                best = candidate

            if current + other == 0:
                break

        if best is None:
            raise AdjustmentError("송금 경로를 계산할 수 없습니다.")
        return best

    # 최소 송금 해가 만든 연결 그룹을 구한 뒤, 각 그룹 안에서 실제 채무액만
    # 오가도록 다시 매칭한다. 중간 사람이 과다 송금 후 돌려받는 결과를 막는다.
    minimum_edges = solve(initial_state)
    graph: dict[int, set[int]] = {index: set() for index in range(len(names))}
    for left, right in minimum_edges:
        graph[left].add(right)
        graph[right].add(left)

    components: list[list[str]] = []
    remaining = set(graph)
    while remaining:
        first = min(remaining)
        remaining.remove(first)
        stack = [first]
        component = [first]
        while stack:
            current = stack.pop()
            for neighbor in sorted(graph[current]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
                    component.append(neighbor)
        components.append([names[index] for index in component])

    transfers: list[Transfer] = []
    for component in components:
        component_balances = {name: balances[name] for name in component}
        transfers.extend(_calculate_greedy_transfers(component_balances))
    return tuple(transfers)


def _calculate_greedy_transfers(
    balances: dict[str, int],
) -> tuple[Transfer, ...]:
    debtors = [[name, -balance] for name, balance in balances.items() if balance < 0]
    creditors = [[name, balance] for name, balance in balances.items() if balance > 0]
    debtors.sort(key=lambda item: (-int(item[1]), str(item[0])))
    creditors.sort(key=lambda item: (-int(item[1]), str(item[0])))

    transfers: list[Transfer] = []
    debtor_index = 0
    creditor_index = 0
    while debtor_index < len(debtors) and creditor_index < len(creditors):
        sender, debt = debtors[debtor_index]
        receiver, credit = creditors[creditor_index]
        amount = min(int(debt), int(credit))
        if amount > 0:
            transfers.append(Transfer(str(sender), str(receiver), amount))

        debtors[debtor_index][1] = int(debt) - amount
        creditors[creditor_index][1] = int(credit) - amount
        if debtors[debtor_index][1] == 0:
            debtor_index += 1
        if creditors[creditor_index][1] == 0:
            creditor_index += 1

    if any(int(item[1]) for item in debtors[debtor_index:]) or any(
        int(item[1]) for item in creditors[creditor_index:]
    ):
        raise AdjustmentError("송금 경로의 합계가 맞지 않습니다.")
    return tuple(transfers)


def _load_data() -> dict[str, Any]:
    if not storage.isExist(ADJUSTMENT_STORAGE_NAME):
        return {"version": 1, "chats": {}}

    data = storage.get(ADJUSTMENT_STORAGE_NAME)
    if not isinstance(data, dict):
        raise AdjustmentError("정산 저장 파일 형식이 올바르지 않습니다.")
    if not isinstance(data.get("chats"), dict):
        data["chats"] = {}
    data.setdefault("version", 1)
    return data


def _save_data(data: dict[str, Any]) -> None:
    if storage.isExist(ADJUSTMENT_STORAGE_NAME):
        storage.update(ADJUSTMENT_STORAGE_NAME, data)
    else:
        storage.create(ADJUSTMENT_STORAGE_NAME, data)


def _get_rooms(
    data: dict[str, Any],
    chat_id: int | str,
    *,
    create: bool = False,
) -> dict[str, Any]:
    chats = data.get("chats")
    if not isinstance(chats, dict):
        raise AdjustmentError("정산 저장 파일 형식이 올바르지 않습니다.")

    chat_key = str(chat_id)
    chat_data = chats.get(chat_key)
    if chat_data is None and create:
        chat_data = {"rooms": {}}
        chats[chat_key] = chat_data
    if chat_data is None:
        return {}
    if not isinstance(chat_data, dict) or not isinstance(chat_data.get("rooms"), dict):
        raise AdjustmentError("정산 저장 파일 형식이 올바르지 않습니다.")
    return chat_data["rooms"]


def _room_participant_count(room: dict[str, Any]) -> int:
    participant_count = room.get("participant_count")
    if not isinstance(participant_count, int) or isinstance(participant_count, bool):
        raise AdjustmentError("저장된 정산 인원수가 올바르지 않습니다.")
    if not MIN_PARTICIPANTS <= participant_count <= MAX_PARTICIPANTS:
        raise AdjustmentError("저장된 정산 인원수가 범위를 벗어났습니다.")
    return participant_count


def _room_members(room: dict[str, Any]) -> dict[str, Any]:
    members = room.get("members")
    if not isinstance(members, dict):
        raise AdjustmentError("저장된 참여자 정보가 올바르지 않습니다.")
    return members


def _non_negative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AdjustmentError(f"{label}이 올바르지 않습니다.")
    return value


def _validate_name(value: str, label: str, max_length: int) -> str:
    value = value.strip()
    if not value:
        raise AdjustmentError(f"{label}을 입력해 주세요.")
    if len(value) > max_length:
        raise AdjustmentError(f"{label}은 {max_length}자 이내로 입력해 주세요.")
    return value
