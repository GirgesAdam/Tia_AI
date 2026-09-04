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
    old = '''        if prefetch_direct is None and str(semantic_decision.package_intent) in {"purchase", "inquire"}:
            package_intent_reply = _verified_package_intent_reply(
'''
    new = '''        if (
            prefetch_direct is None
            and "package_refund_quote" not in policy.capabilities
            and str(semantic_decision.package_intent) in {"purchase", "inquire"}
        ):
            package_intent_reply = _verified_package_intent_reply(
'''
    content = _replace_once(content, old, new, label="package refund precedence")
    _write(path, content)


def patch_interpreter() -> None:
    path = "backend/app/agents/turn_interpreter.py"
    content = _read(path)
    old = '''        "active booking request, the package intent owns the turn. A package cancellation refund amount is "
        "package_refund_quote and is read-only.\\n\\n"
'''
    new = '''        "active booking request, the package intent owns the turn. A pure package cancellation refund amount "
        "question uses package_refund_quote, is read-only, and should use package_intent=none rather than a "
        "generic package inquiry. Comparing an ordinary paid session with using or buying a package is "
        "commercial/booking guidance, not a medical question. Escalate for medical risk only when the customer "
        "asks about clinical suitability, diagnosis, safety, contraindications, adverse effects, or a "
        "health-based treatment recommendation.\\n\\n"
'''
    content = _replace_once(content, old, new, label="package semantic guidance")
    _write(path, content)


def patch_live_runner() -> None:
    path = "backend/scripts/run_live_agent_ux_review.py"
    content = _read(path)

    start = content.index("def _booking_context(db: Session, workspace: Workspace):\n")
    end = content.index("\ndef _seed_upcoming", start)
    new_context = '''def _booking_context(db: Session, workspace: Workspace):
    """Pick a real bookable service/doctor from the staging catalog.

    The live review must adapt to the clinic data instead of depending on a demo-only
    service slug. Location IDs remain internal fixtures and are never shown to the customer.
    """
    catalog = build_clinic_catalog(db, workspace)
    services = [row for row in catalog.get("services", []) if isinstance(row, dict) and row.get("id")]
    doctors = [row for row in catalog.get("doctors", []) if isinstance(row, dict) and row.get("id")]
    if not services:
        raise RuntimeError("No services available in staging catalog")
    if not doctors:
        raise RuntimeError("No doctors available in staging catalog")

    adapter = get_clinic_adapter(db=db, workspace=workspace)
    adapter.require_capability(ClinicCapability.AVAILABILITY_READ)
    today = datetime.now(UTC).date()
    primary_branch_id = str(workspace.primary_branch_id or "")

    for service in services:
        service_id = str(service["id"])
        compatible_doctors = [
            doctor
            for doctor in doctors
            if service_id in {str(value) for value in (doctor.get("service_ids") or [])}
        ]
        for doctor in compatible_doctors:
            scheduled = [
                str(value)
                for value in (doctor.get("scheduled_branch_ids") or doctor.get("branch_ids") or [])
                if value
            ]
            branch_ids: list[str] = []
            if primary_branch_id and (not scheduled or primary_branch_id in scheduled):
                branch_ids.append(primary_branch_id)
            branch_ids.extend(value for value in scheduled if value not in branch_ids)
            if not branch_ids and primary_branch_id:
                branch_ids.append(primary_branch_id)
            for branch_id in branch_ids:
                for offset in range(1, 36):
                    day = today + timedelta(days=offset)
                    available = adapter.get_availability(
                        AvailabilityRequest(
                            branch_id=branch_id,
                            service_id=service_id,
                            booking_date=day,
                            doctor_id=str(doctor["id"]),
                        )
                    )
                    if available.slots:
                        return catalog, service, doctor, branch_id, day, available
    raise RuntimeError("No bookable service with future availability in 35 days")
'''
    content = content[:start] + new_context + content[end:]

    old_names = '''        "package_compare", "package_refund", "history", "medical_handoff", "privacy", "mixed_language",
'''
    new_names = '''        "package_compare", "package_refund", "history", "medical_handoff", "privacy", "mixed_language",
        "service_change_mid_flow",
'''
    content = _replace_once(content, old_names, new_names, label="enable service-change case")

    anchor = '''        if name == "medical_handoff":
            medical_ok = any(token in replies for token in ("الفريق الطبي", "فريق العيادة", "تقييم", "طبي"))
            checks.append(f"medical_handoff={medical_ok}")
            scenario_ok = scenario_ok and medical_ok

        result.checks = checks
'''
    replacement = '''        if name == "medical_handoff":
            medical_ok = any(token in replies for token in ("الفريق الطبي", "فريق العيادة", "تقييم", "طبي"))
            checks.append(f"medical_handoff={medical_ok}")
            scenario_ok = scenario_ok and medical_ok
        if name == "package_compare":
            all_replied = all(bool((turn.assistant or "").strip()) for turn in result.turns)
            lowered_replies = replies.casefold()
            mentions_package = "باكدج" in replies or "package" in lowered_replies
            no_medical_handoff = not any(
                token in replies
                for token in ("الفريق الطبي", "فريق العيادة", "تقييم طبي", "تحويل المحادثة")
            )
            comparison_ok = all_replied and mentions_package and no_medical_handoff
            checks.append(f"commercial_package_comparison={comparison_ok}")
            scenario_ok = scenario_ok and comparison_ok
        if name == "package_refund":
            all_replied = all(bool((turn.assistant or "").strip()) for turn in result.turns)
            lowered_replies = replies.casefold()
            refund_language = any(token in replies for token in ("يرجع", "استرداد", "هترجع")) or "refund" in lowered_replies
            money_language = "جنيه" in replies or "egp" in lowered_replies
            refund_ok = all_replied and refund_language and money_language
            checks.append(f"refund_amount_answered={refund_ok}")
            scenario_ok = scenario_ok and refund_ok

        result.checks = checks
'''
    content = _replace_once(content, anchor, replacement, label="truthful package assertions")
    _write(path, content)


def main() -> None:
    patch_agent_chat()
    patch_interpreter()
    patch_live_runner()
    print("Agent UX continuation patch applied.")


if __name__ == "__main__":
    main()
