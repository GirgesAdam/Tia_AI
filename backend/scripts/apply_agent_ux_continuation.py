from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def _replace_once(content: str, old: str, new: str, *, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return content.replace(old, new, 1)


def patch_agent_chat() -> None:
    path = "backend/app/services/agent_chat.py"
    content = _read(path)
    old = '''            and str(semantic_decision.package_intent) in {"purchase", "inquire"}
'''
    new = '''            and str(semantic_decision.package_intent) == "purchase"
'''
    content = _replace_once(
        content,
        old,
        new,
        label="let package inquiries use grounded conversational composition",
    )
    _write(path, content)


def patch_interpreter() -> None:
    path = "backend/app/agents/turn_interpreter.py"
    content = _read(path)
    old = '''        "asks about clinical suitability, diagnosis, safety, contraindications, adverse effects, or a "
        "health-based treatment recommendation.\\n\\n"
'''
    new = '''        "asks about clinical suitability, diagnosis, safety, contraindications, adverse effects, or a "
        "health-based treatment recommendation. A catalog flag saying a service requires medical review does "
        "not by itself make a price, availability, booking, reschedule, or cancellation request medical; keep "
        "those operational unless the customer's actual question asks for clinical judgment.\\n\\n"
'''
    content = _replace_once(content, old, new, label="operational requests are not medical handoffs")
    _write(path, content)


def patch_live_runner() -> None:
    path = "backend/scripts/run_live_agent_ux_review.py"
    content = _read(path)

    old_branch_block = '''            branch_ids: list[str] = []
            if primary_branch_id and (not scheduled or primary_branch_id in scheduled):
                branch_ids.append(primary_branch_id)
            branch_ids.extend(value for value in scheduled if value not in branch_ids)
            if not branch_ids and primary_branch_id:
                branch_ids.append(primary_branch_id)
            for branch_id in branch_ids:
'''
    new_branch_block = '''            if not primary_branch_id:
                raise RuntimeError("Single-location staging workspace has no primary branch")
            if scheduled and primary_branch_id not in scheduled:
                continue
            for branch_id in [primary_branch_id]:
'''
    content = _replace_once(
        content,
        old_branch_block,
        new_branch_block,
        label="live fixtures must use the same single location as the agent",
    )

    old_seed = '''    selected = list(available.slots[:count])
    if len(selected) < count:
        adapter = get_clinic_adapter(db=db, workspace=workspace)
        day = available.slots[0].start_at.date() + timedelta(days=1)
        while len(selected) < count and day <= available.slots[0].start_at.date() + timedelta(days=35):
            extra = adapter.get_availability(
                AvailabilityRequest(
                    branch_id=branch_id,
                    service_id=str(service_row["id"]),
                    booking_date=day,
                    doctor_id=str(doctor["id"]),
                )
            )
            if extra.slots:
                selected.append(extra.slots[0])
            day += timedelta(days=1)
'''
    new_seed = '''    selected = []

    def add_non_overlapping(candidates) -> None:
        for candidate in candidates:
            overlaps = any(
                candidate.start_at < chosen.end_at and chosen.start_at < candidate.end_at
                for chosen in selected
            )
            if not overlaps:
                selected.append(candidate)
                if len(selected) >= count:
                    return

    add_non_overlapping(available.slots)
    if len(selected) < count:
        adapter = get_clinic_adapter(db=db, workspace=workspace)
        day = available.slots[0].start_at.date() + timedelta(days=1)
        while len(selected) < count and day <= available.slots[0].start_at.date() + timedelta(days=35):
            extra = adapter.get_availability(
                AvailabilityRequest(
                    branch_id=branch_id,
                    service_id=str(service_row["id"]),
                    booking_date=day,
                    doctor_id=str(doctor["id"]),
                )
            )
            add_non_overlapping(extra.slots)
            day += timedelta(days=1)
'''
    content = _replace_once(content, old_seed, new_seed, label="non-overlapping appointment fixtures")

    content = _replace_once(
        content,
        '''    nonempty = any(text.strip() for text in messages)\n''',
        '''    nonempty = bool(messages) and all(text.strip() for text in messages)\n''',
        label="every expected turn must have a reply",
    )
    content = _replace_once(
        content,
        '''        global_ok, checks = _global_reply_checks(result.turns, branches)\n''',
        '''        checked_turns = result.turns[:1] if name == "medical_handoff" else result.turns\n        global_ok, checks = _global_reply_checks(checked_turns, branches)\n''',
        label="allow only intentional post-handoff pause",
    )
    content = _replace_once(
        content,
        '''            second = f"خليه يوم {day.isoformat()} الساعة {local.strftime('%H:%M')} مع {doctor.get('name') or 'نفس الدكتور'}"\n''',
        '''            second = f"غيّره دلوقتي ليوم {day.isoformat()} الساعة {local.strftime('%H:%M')} مع {doctor.get('name') or 'نفس الدكتور'}"\n''',
        label="explicit reschedule authorization",
    )

    old_compare = '''            comparison_ok = all_replied and mentions_package and no_medical_handoff
'''
    new_compare = '''            comparison_language = any(
                token in replies
                for token in ("استخدم", "استخدام", "جلسة منفصلة", "جلسة واحدة", "الأفضل", "أفضل", "بدل")
            )
            comparison_ok = all_replied and mentions_package and comparison_language and no_medical_handoff
'''
    content = _replace_once(content, old_compare, new_compare, label="package comparison must answer the choice")

    anchor = '''        if name == "package_refund":
            all_replied = all(bool((turn.assistant or "").strip()) for turn in result.turns)
'''
    addition = '''        if name in {"availability_window", "service_change_mid_flow"}:
            no_false_medical_handoff = not any(
                token in replies for token in ("الفريق الطبي", "تحويل المحادثة", "حوّلت المحادثة")
            )
            checks.append(f"no_false_medical_handoff={no_false_medical_handoff}")
            scenario_ok = scenario_ok and no_false_medical_handoff
        if name == "package_refund":
            all_replied = all(bool((turn.assistant or "").strip()) for turn in result.turns)
'''
    content = _replace_once(content, anchor, addition, label="operational handoff assertion")
    _write(path, content)


def main() -> None:
    patch_agent_chat()
    patch_interpreter()
    patch_live_runner()
    print("Agent UX continuation patch applied.")


if __name__ == "__main__":
    main()
