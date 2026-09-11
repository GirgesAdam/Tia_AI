from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agents.v2.responder import compose_v2_customer_reply
from app.agents.v2.semantic_context import SemanticContext, build_semantic_context
from app.agents.v2.turn_interpreter import interpret_customer_turn_v2
from app.services.agent_v2.outcome_builder import build_handoff_outcome, build_step_outcome
from app.services.agent_v2.planner import (
    PlannerContext,
    advance_step_after_verification,
    plan_turn,
)
from app.services.agent_v2.read_executor import ReadExecutionBundle, ReadResult
from app.services.agent_v2.test_harness import (
    DEFAULT_CATALOG,
    V2FixtureEnvironment,
    V2HarnessResult,
    V2HarnessStepTrace,
    execute_fixture_reads,
)

TZ = "Africa/Cairo"
NOW = datetime(2026, 9, 11, 21, 30, tzinfo=ZoneInfo(TZ))

KNOWLEDGE_TEXT = """نحن عيادة متخصصة في الليزر والعناية بالبشرة والتجميل غير الجراحي. نقدم إزالة الشعر بالليزر لمناطق الجسم المختلفة، جلسات هيدرافيشل وتنظيف البشرة، جلسات فراكشنال، واستشارات جلدية وتجميلية حسب احتياج كل حالة.

في إزالة الشعر بالليزر نستخدم جهازي Candela Gentle وPrime Lase. نستخدم Candela غالبًا للحالات التي تحتاج نبضات دقيقة مع نظام تبريد أثناء الجلسة، بينما Prime Lase مناسب أيضًا لإزالة الشعر ويتميز بسرعة تغطية المساحات الكبيرة. اختيار الجهاز الأنسب يتم حسب نوع البشرة والشعر والمنطقة وتقييم المختص، وليس لأن جهازًا واحدًا أفضل لكل الحالات.

الهيدرافيشل جلسة عناية بالبشرة تساعد على التنظيف والترطيب وتحسين مظهر البشرة. الفراكشنال يستخدم لتحسين ملمس البشرة وآثار الحبوب والمسام حسب تقييم الطبيب وملاءمة الحالة.

قبل جلسة إزالة الشعر بالليزر يفضّل حلاقة المنطقة بالموس وتجنب إزالة الشعر من الجذور بالشمع أو الحلاوة قبل الجلسة. لو في التهاب شديد أو تهيج بالجلد أو استخدام أدوية أو علاجات جلدية حديثة، يجب إبلاغ المختص قبل الجلسة.

لو العميل غير متأكد من الخدمة أو الجهاز الأنسب له، نرشح له حجز استشارة أو تقييم مع المختص قبل اختيار الجلسة."""


@dataclass(frozen=True)
class ConversationCase:
    title: str
    turns: tuple[str, ...]


CONVERSATIONS = (
    ConversationCase(
        "شرح خدمة ثم السعر والمدة",
        (
            "الهيدرافيشل بيعمل إيه؟",
            "طب بكام وبيستغرق قد إيه؟",
        ),
    ),
    ConversationCase(
        "مقارنة أجهزة ثم توافر كانديلا",
        (
            "إيه الفرق بين كانديلا وبرايم ليز؟",
            "طيب ليزر الإبط متاح بكرة بعد 6 على كانديلا؟",
        ),
    ),
    ConversationCase(
        "عرض المواعيد ثم الحجز من السياق",
        (
            "إيه المتاح بكرة لليزر إبط مع د مريم بعد 6؟",
            "احجزلي الساعة 8 مع د مريم",
        ),
    ),
    ConversationCase(
        "حجز الساعة 7 يحتاج اختيار دكتور",
        (
            "احجزلي ليزر إبط بكرة الساعة 7",
            "خليه مع د مريم",
        ),
    ),
    ConversationCase(
        "ساعات العيادة وتفسير الساعة 8",
        (
            "العيادة بتقفل الساعة كام؟",
            "احجزلي ليزر إبط بكرة الساعة 8 مع د مريم",
        ),
    ),
    ConversationCase(
        "موعد غير متاح ثم اختيار بديل",
        (
            "احجزلي ليزر إبط بكرة الساعة 9 مع د سارة",
            "طيب احجزلي الساعة 8 مع د مريم بدلها",
        ),
    ),
    ConversationCase(
        "عرض موعد قائم ثم تغيير الموعد",
        (
            "موعد الليزر الجاي امتى؟",
            "غيريه لبكرة الساعة 8 مع د مريم",
        ),
    ),
    ConversationCase(
        "عرض موعد هيدرافيشل ثم إلغاؤه",
        (
            "عندي ميعاد هيدرافيشل امتى؟",
            "الغيه",
        ),
    ),
    ConversationCase(
        "موعد ينتظر التأكيد ثم تأكيده",
        (
            "عندي ميعاد مستني تأكيد؟",
            "أكدلي ميعاد الهيدرافيشل",
        ),
    ),
    ConversationCase(
        "رصيد الباكيدج ثم الحجز منها",
        (
            "فاضلي كام جلسة في باكيدج الإبط؟",
            "احجزلي جلسة منها بكرة الساعة 6 مع د مريم",
        ),
    ),
    ConversationCase(
        "وجود باكيدج مع طلب عدم استخدامها",
        (
            "عندي باكيدج إبط شغالة؟",
            "احجزلي بكرة الساعة 8 مع د مريم بس متستخدمش الباكيدج",
        ),
    ),
    ConversationCase(
        "رصيد حالي ثم شراء باكيدج جديدة",
        (
            "الباكيدج اللي عندي فيها كام جلسة؟",
            "عايزة أشتري باكيدج 6 جلسات إبط كانديلا كمان",
        ),
    ),
    ConversationCase(
        "قيمة استرداد الباكيدج ثم طلب الإلغاء",
        (
            "لو لغيت باكيدج الإبط هرجع كام؟",
            "تمام، عايزة ألغيه",
        ),
    ),
    ConversationCase(
        "سعر وتوافر ثم حجز البكيني",
        (
            "ليزر بكيني بكام وإيه المتاح بكرة بعد 7؟",
            "لو الساعة 8 موجودة مع د مريم احجزيها",
        ),
    ),
    ConversationCase(
        "دكاترة الهيدرافيشل ثم تعليمات الخدمة",
        (
            "مين الدكاترة اللي بيعملوا هيدرافيشل؟",
            "وعندكم ايه تعليمات عنه قبل الجلسة؟",
        ),
    ),
)


def _test_environment() -> V2FixtureEnvironment:
    catalog = deepcopy(DEFAULT_CATALOG)
    for service in catalog.get("services", []):
        if isinstance(service, dict):
            service.pop("description", None)
    catalog["branches"] = [
        {
            "id": "single-location",
            "name": "Tia Test Clinic",
            "phone": "01000000000",
            "address": "القاهرة",
            "city": "Cairo",
            "timezone": TZ,
            "working_hours": [
                {"weekday": weekday, "start": "10:00", "end": "22:00"}
                for weekday in range(7)
            ],
        }
    ]
    return V2FixtureEnvironment(
        catalog=catalog,
        clinic_info={
            "clinic_name": "Tia Test Clinic",
            "phone": "01000000000",
            "timezone": TZ,
            "locations": [{"name": "Tia Test Clinic", "city": "Cairo"}],
            "working_hours": "يوميًا من 10 صباحًا إلى 10 مساءً",
        },
    )


def _ground_explanatory_reads(
    bundle: ReadExecutionBundle,
    *,
    operation_type: str,
) -> ReadExecutionBundle:
    results: list[ReadResult] = []
    for result in bundle.results:
        payload = deepcopy(result.payload)
        if result.kind == "service_catalog":
            service = payload.get("service")
            if isinstance(service, dict):
                service.pop("description", None)
                if operation_type == "service_info":
                    service["description"] = KNOWLEDGE_TEXT
        elif result.kind == "clinic_info":
            payload["knowledge"] = KNOWLEDGE_TEXT
        results.append(
            ReadResult(
                kind=result.kind,
                ok=result.ok,
                payload=payload,
                error_code=result.error_code,
            )
        )
    return ReadExecutionBundle(results=results, verification=bundle.verification)


def _run_turn(*, history: list[BaseMessage], env: V2FixtureEnvironment) -> V2HarnessResult:
    semantic_context: SemanticContext = build_semantic_context(env.catalog)
    understanding = interpret_customer_turn_v2(
        history=history,
        semantic_context=semantic_context,
        timezone_name=TZ,
        local_now=NOW,
    )
    plan = plan_turn(
        understanding,
        PlannerContext(semantic_context=semantic_context, active_task=None, now=NOW),
    )

    if plan.handoff_category is not None:
        outcome = build_handoff_outcome(plan)
        reply, model = compose_v2_customer_reply(
            clinic_name="Tia Test Clinic",
            timezone_name=TZ,
            local_now=NOW,
            history=history,
            outcomes=[outcome],
        )
        return V2HarnessResult(
            understanding=understanding,
            plan=plan,
            traces=(),
            outcomes=(outcome,),
            reply=reply,
            responder_model=model,
        )

    traces: list[V2HarnessStepTrace] = []
    outcomes = []
    for step in plan.steps:
        raw_bundle = execute_fixture_reads(step, env) if step.reads else ReadExecutionBundle()
        bundle = _ground_explanatory_reads(raw_bundle, operation_type=step.operation_type)
        advanced = (
            advance_step_after_verification(step, bundle.verification)
            if step.write_intent is not None and step.reads
            else step
        )
        simulated_write = None
        action_result = None
        if advanced.disposition == "write_ready":
            simulated_write = advanced.write_intent.kind if advanced.write_intent is not None else None
            action_result = {"ok": True}

        outcome = build_step_outcome(
            advanced,
            turn=understanding,
            semantic_context=semantic_context,
            reads=bundle if bundle.results else None,
            action_result=action_result,
        )
        traces.append(
            V2HarnessStepTrace(
                operation_index=advanced.operation_index,
                operation_type=advanced.operation_type,
                disposition_before=step.disposition,
                disposition_after=advanced.disposition,
                read_kinds=tuple(str(result.kind) for result in bundle.results),
                simulated_write=simulated_write,
                outcome=outcome,
            )
        )
        outcomes.append(outcome)

    reply, model = compose_v2_customer_reply(
        clinic_name="Tia Test Clinic",
        timezone_name=TZ,
        local_now=NOW,
        history=history,
        outcomes=outcomes,
    )
    return V2HarnessResult(
        understanding=understanding,
        plan=plan,
        traces=tuple(traces),
        outcomes=tuple(outcomes),
        reply=reply,
        responder_model=model,
    )


def _compact_result(result: V2HarnessResult) -> dict[str, object]:
    return {
        "operations": [operation.type for operation in result.understanding.operations],
        "plan": [
            {
                "operation": step.operation_type,
                "disposition": step.disposition,
                "response_goal": step.response_goal,
                "reads": [str(read.kind) for read in step.reads],
                "write": step.write_intent.kind if step.write_intent is not None else None,
            }
            for step in result.plan.steps
        ],
        "outcomes": [
            {
                "status": outcome.status,
                "response_goal": outcome.response_goal,
            }
            for outcome in result.outcomes
        ],
        "simulated_writes": [
            trace.simulated_write for trace in result.traces if trace.simulated_write is not None
        ],
        "model": result.responder_model,
    }


def main() -> None:
    print("TIA V2 — 15 NEW CONVERSATIONS / 30 TURNS")
    print("V1 is never called. Writes are simulated and never persisted.\n")
    total_turns = 0
    simulated_writes = 0

    for index, case in enumerate(CONVERSATIONS, start=1):
        print("#" * 100)
        print(f"CONVERSATION {index:02d}: {case.title}")
        print("#" * 100)
        env = _test_environment()
        history: list[BaseMessage] = []

        for turn_index, customer_text in enumerate(case.turns, start=1):
            turn_history = [*history, HumanMessage(content=customer_text)]
            result = _run_turn(history=turn_history, env=env)
            meta = _compact_result(result)
            print(f"\nTURN {turn_index}")
            print(f"CUSTOMER: {customer_text}")
            print("V2_META:", json.dumps(meta, ensure_ascii=False, default=str))
            print(f"TIA V2: {result.reply}")
            if meta["simulated_writes"]:
                print("[SIMULATED WRITE — NO DATABASE MUTATION]")
                simulated_writes += len(meta["simulated_writes"])
            history.extend([HumanMessage(content=customer_text), AIMessage(content=result.reply)])
            total_turns += 1

        print()

    print("=" * 100)
    print(
        json.dumps(
            {
                "conversations": len(CONVERSATIONS),
                "turns": total_turns,
                "simulated_writes": simulated_writes,
                "v1_called": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
