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
    old = '''        if grounded_mode and not model_name.startswith("flow-interpreter:deterministic-"):\n'''
    new = '''        if (\n            grounded_mode\n            and model_name != "capability-policy:handoff"\n            and not model_name.startswith("flow-interpreter:deterministic-")\n        ):\n'''
    content = _replace_once(
        content,
        old,
        new,
        label="preserve deterministic handoff acknowledgement",
    )
    _write(path, content)


def patch_live_runner() -> None:
    path = "backend/scripts/run_live_agent_ux_review.py"
    content = _read(path)

    content = _replace_once(
        content,
        '''            first, second = "عايز ألغي معادي الجاي", "أيوة الغيه"\n''',
        '''            first, second = "فكرني بمعادي الجاي", "تمام، الغيه دلوقتي"\n''',
        label="natural two-turn cancellation",
    )

    old_medical = '''        if name == "medical_handoff":\n            medical_ok = any(token in replies for token in ("الفريق الطبي", "فريق العيادة", "تقييم", "طبي"))\n            checks.append(f"medical_handoff={medical_ok}")\n            scenario_ok = scenario_ok and medical_ok\n'''
    new_medical = '''        if name == "medical_handoff":\n            expected = "الموضوع ده محتاج تقييم من الفريق الطبي، فحوّلت المحادثة لفريق العيادة للمراجعة."\n            first_reply = (result.turns[0].assistant or "").strip() if result.turns else ""\n            medical_ok = first_reply == expected\n            checks.append(f"safe_deterministic_medical_handoff={medical_ok}")\n            scenario_ok = scenario_ok and medical_ok\n'''
    content = _replace_once(content, old_medical, new_medical, label="safe medical handoff assertion")
    _write(path, content)


def main() -> None:
    patch_agent_chat()
    patch_live_runner()
    print("Agent UX continuation patch applied.")


if __name__ == "__main__":
    main()
