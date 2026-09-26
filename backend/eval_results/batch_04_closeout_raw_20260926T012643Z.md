# Tia Agent Evaluation — Batch 04 Raw Baseline

- Batch runtime base SHA: b49ee2ffde9f45172bd553a57b7236808b0bf9a4
- Harness SHA: b49ee2ffde9f45172bd553a57b7236808b0bf9a4
- Scenario version: batch4-v1
- Model: gpt-5.6-luna
- Reasoning: low
- Scenarios executed: 17

Raw deterministic findings are guards; final conversational verdict requires manual review.

## b4_01_book_then_modify_after_gap

Category: multi_day_lifecycle
Purpose: Resolve a days-old booking from canonical upcoming appointments without relying on stale active-task state.
Review status: PENDING_MANUAL_REVIEW
Expected: After a five-day conversation gap, canonical appointment state resolves the original booking and only that appointment is rescheduled.

Customer 1: احجزيلي هيدرافيشل يوم 2026-09-29 الساعة 10:00 مع عمر خليل
Tia: تم حجز جلسة الهيدرافيشل يوم 29 سبتمبر 2026 الساعة 10:00 صباحًا مع عمر خليل. السعر 1800 جنيه.
Usage: in=7670 read=5353 write=1558 uncached=759 out=270 latency=12116ms

Customer 2: عايزة أغير ميعاد الحجز اللي عملناه
Tia: أكيد، تحبي تغيّريه ليوم كام؟
Usage: in=7950 read=5353 write=1680 uncached=917 out=352 latency=7788ms

Customer 3: خليه يوم 2026-10-01 الساعة 14:00
Tia: تم تغيير حجز الهيدرافيشل مع عمر خليل ليوم 1 أكتوبر 2026 الساعة 2:00 ظهرًا. السعر 1800 جنيه.
Usage: in=8254 read=5353 write=1984 uncached=917 out=453 latency=14539ms

DB verification:
{
  "source_id": "9eaad0f5-755d-4dd7-842c-43efe0368042",
  "source_date": "2026-09-29",
  "replacement_date": "2026-10-01",
  "replacements": [
    {
      "id": "82d9e402-1a5b-48b8-8b1f-156747723836",
      "status": "confirmed",
      "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
      "doctor_id": "6dd310a2-9f33-568f-b2e0-dd5db0e476c6",
      "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
      "start_at": "2026-10-01T11:00:00+00:00",
      "billing_context": "standard",
      "payment_status": "unknown",
      "amount_paid_minor": null,
      "laser_device_key": null,
      "laser_device_name": null,
      "patient_package_id": null,
      "rescheduled_from_appointment_id": "9eaad0f5-755d-4dd7-842c-43efe0368042"
    }
  ],
  "db_delta": {
    "appointments": {
      "created": [
        "82d9e402-1a5b-48b8-8b1f-156747723836",
        "9eaad0f5-755d-4dd7-842c-43efe0368042"
      ],
      "removed": [],
      "changed": []
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## b4_02_cancel_after_long_gap

Category: multi_day_lifecycle
Purpose: A long-gap cancellation should use the single canonical upcoming appointment rather than stale conversational state.
Review status: PENDING_MANUAL_REVIEW
Expected: With exactly one actionable upcoming appointment, 'الغيه خلاص' cancels that canonical appointment after a long gap.

Customer 1: الغيه خلاص
Tia: تمام، تم إلغاء حجز الهيدرافيشل يوم 30 سبتمبر الساعة 10:00.
Usage: in=7811 read=5353 write=1669 uncached=789 out=421 latency=7980ms

DB verification:
{
  "target_id": "6bb2559f-b335-4717-8d67-4b28fb977d59",
  "appointment_after": {
    "id": "6bb2559f-b335-4717-8d67-4b28fb977d59",
    "status": "cancelled",
    "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
    "doctor_id": "d18b8596-9342-57d9-a03d-6ef674a6f5e0",
    "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
    "start_at": "2026-09-30T07:00:00+00:00",
    "billing_context": "standard",
    "payment_status": "unpaid",
    "amount_paid_minor": null,
    "laser_device_key": null,
    "laser_device_name": null,
    "patient_package_id": null,
    "rescheduled_from_appointment_id": null
  },
  "history_gap_days": 120,
  "db_delta": {
    "appointments": {
      "created": [],
      "removed": [],
      "changed": [
        "6bb2559f-b335-4717-8d67-4b28fb977d59"
      ]
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## b4_03_completed_appointment_not_actionable

Category: multi_day_lifecycle
Purpose: Completed historical appointments must never remain actionable lifecycle targets.
Review status: PENDING_MANUAL_REVIEW
Expected: The completed appointment remains completed and no reschedule write occurs.

Customer 1: غيري الميعاد
Tia: أكيد، تحبي تغيّري الميعاد ليوم إيه؟
Usage: in=7370 read=5353 write=1278 uncached=739 out=210 latency=5887ms

DB verification:
{
  "completed_id": "86e96c8b-4442-4ce3-8ff9-3b14564cac96",
  "appointment_after": {
    "id": "86e96c8b-4442-4ce3-8ff9-3b14564cac96",
    "status": "completed",
    "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
    "doctor_id": "99902579-0e39-5df6-8f01-633b1ea859ef",
    "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
    "start_at": "2026-09-20T01:20:02.295162+00:00",
    "billing_context": "standard",
    "payment_status": "paid",
    "amount_paid_minor": 180000,
    "laser_device_key": null,
    "laser_device_name": null,
    "patient_package_id": null,
    "rescheduled_from_appointment_id": null
  },
  "db_delta": {
    "appointments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## b4_04_financial_handoff_then_return_later

Category: handoff_across_time
Purpose: A financial handoff must not contaminate a fresh booking after handback and a multi-day gap.
Review status: PENDING_MANUAL_REVIEW
Expected: After handback and a four-day gap, the fresh booking succeeds with no stale financial mutation.

Customer 1: فاضل عليا كام فلوس؟
Tia: الموضوع محتاج مراجعة من الاستقبال عشان يحددوا المبلغ المتبقي بدقة، وهما هيتواصلوا معاكي.
Usage: in=7363 read=5353 write=1267 uncached=743 out=182 latency=6268ms

Customer 2: عايزة أحجز هيدرافيشل يوم 2026-09-29 الساعة 10:00 مع عمر خليل
Tia: تم حجز جلسة الهيدرافيشل يوم 29 سبتمبر 2026 الساعة 10:00 صباحًا مع عمر خليل. السعر 1800 جنيه.
Usage: in=7814 read=5353 write=1630 uncached=831 out=363 latency=8131ms

DB verification:
{
  "staff_evidence": {
    "before_staff": {
      "conversation_id": "4a96b99c-d948-4bf7-a7d4-1f012f36ebaf",
      "owner_type": "human",
      "status": "pending",
      "assigned_user_id": null,
      "ownership_epoch": "2026-09-26T01:20:18.949448+00:00",
      "active_handoff_id": "49c4da9a-5a65-4276-a723-031c9c716106",
      "active_handoff_status": "pending"
    },
    "during_staff": {
      "conversation_id": "4a96b99c-d948-4bf7-a7d4-1f012f36ebaf",
      "owner_type": "human",
      "status": "pending",
      "assigned_user_id": "511d5ace-5587-40d7-9312-39adc1cacd73",
      "ownership_epoch": "2026-09-26T01:20:20.031160+00:00",
      "active_handoff_id": "49c4da9a-5a65-4276-a723-031c9c716106",
      "active_handoff_status": "claimed"
    },
    "after_handback": {
      "conversation_id": "4a96b99c-d948-4bf7-a7d4-1f012f36ebaf",
      "owner_type": "ai",
      "status": "open",
      "assigned_user_id": null,
      "ownership_epoch": "2026-09-26T01:20:20.814133+00:00",
      "active_handoff_id": null,
      "active_handoff_status": null
    },
    "staff_message_id": "ebd34dd8-2a4f-439d-91ce-d514a786dfb6",
    "staff_message": "راجعنا الحساب، ولو محتاجة تفاصيل أكتر كلمينا."
  },
  "created": [
    {
      "id": "7acac956-31b1-4602-94b4-4655fd49b196",
      "status": "confirmed",
      "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
      "doctor_id": "6dd310a2-9f33-568f-b2e0-dd5db0e476c6",
      "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
      "start_at": "2026-09-29T07:00:00+00:00",
      "billing_context": "standard",
      "payment_status": "unknown",
      "amount_paid_minor": null,
      "laser_device_key": null,
      "laser_device_name": null,
      "patient_package_id": null,
      "rescheduled_from_appointment_id": null
    }
  ],
  "db_delta": {
    "appointments": {
      "created": [
        "7acac956-31b1-4602-94b4-4655fd49b196"
      ],
      "removed": [],
      "changed": []
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [
        "49c4da9a-5a65-4276-a723-031c9c716106"
      ],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": [
    {
      "status": "pending",
      "category": "payment",
      "priority": "normal",
      "source": "ai"
    }
  ]
}
Deterministic findings: none; manual review still required.

## b4_05_reception_modifies_then_handback

Category: handoff_across_time
Purpose: After Reception edits an appointment, the Agent must read the new canonical DB truth after handback.
Review status: PENDING_MANUAL_REVIEW
Expected: The Agent answers from the Reception-updated appointment and performs no stale-state write.

Customer 1: هاي
Tia: أهلاً بيكي! إزاي أقدر أساعدك؟
Usage: in=7339 read=5353 write=1251 uncached=735 out=164 latency=5667ms

Customer 2: ميعادي بقى امتى؟
Tia: ميعادك يوم الخميس 1 أكتوبر الساعة 2:00 ظهرًا في Tia Clinic مع د. عمر خليل لجلسة هيدرافيشل، وسعرها 1800 جنيه.
Usage: in=7729 read=5353 write=1590 uncached=786 out=228 latency=6886ms

DB verification:
{
  "ownership": {
    "before_takeover": {
      "conversation_id": "3a5d5ec3-0626-48d2-8b6d-2cf8f6343cfd",
      "owner_type": "ai",
      "status": "open",
      "assigned_user_id": null,
      "ownership_epoch": "2026-09-26T01:20:35.142944+00:00",
      "active_handoff_id": null,
      "active_handoff_status": null
    },
    "human_owned": {
      "conversation_id": "3a5d5ec3-0626-48d2-8b6d-2cf8f6343cfd",
      "owner_type": "human",
      "status": "pending",
      "assigned_user_id": "511d5ace-5587-40d7-9312-39adc1cacd73",
      "ownership_epoch": "2026-09-26T01:20:42.345584+00:00",
      "active_handoff_id": "cc6b0c82-6b2d-44a3-999a-fff7a5e6ea59",
      "active_handoff_status": "claimed"
    },
    "staff_message_id": "721afd9e-7ecb-4140-87c3-ab1adc4d8ed5",
    "staff_message": "تمام، هعدّل الميعاد من الريسبشن."
  },
  "handback": {
    "conversation_id": "3a5d5ec3-0626-48d2-8b6d-2cf8f6343cfd",
    "owner_type": "ai",
    "status": "open",
    "assigned_user_id": null,
    "ownership_epoch": "2026-09-26T01:20:45.064390+00:00",
    "active_handoff_id": null,
    "active_handoff_status": null
  },
  "target_date": "2026-10-01",
  "target_time": "14:00",
  "appointment_after": {
    "id": "521f839e-b960-41ca-a3c2-b8f82b51aa04",
    "status": "confirmed",
    "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
    "doctor_id": "6dd310a2-9f33-568f-b2e0-dd5db0e476c6",
    "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
    "start_at": "2026-10-01T11:00:00+00:00",
    "billing_context": "standard",
    "payment_status": "unpaid",
    "amount_paid_minor": null,
    "laser_device_key": null,
    "laser_device_name": null,
    "patient_package_id": null,
    "rescheduled_from_appointment_id": null
  },
  "db_delta": {
    "appointments": {
      "created": [],
      "removed": [],
      "changed": [
        "521f839e-b960-41ca-a3c2-b8f82b51aa04"
      ]
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [
        "cc6b0c82-6b2d-44a3-999a-fff7a5e6ea59"
      ],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## b4_06_multiple_messages_while_human_owns

Category: handoff_across_time
Purpose: Several customer messages during human ownership must remain AI-silent and must not replay after handback.
Review status: PENDING_MANUAL_REVIEW
Expected: All human-owned inbound turns are silent/no-write; after handback only the fresh price question is answered.

Customer 1: هاي
Tia: أهلاً! إزاي أقدر أساعدك؟
Usage: in=7339 read=5353 write=1251 uncached=735 out=162 latency=6442ms

Customer 2: ممكن أغير ميعادي؟
Tia: None
Usage: in=0 read=0 write=0 uncached=0 out=0 latency=602ms

Customer 3: وخليه الجمعة
Tia: None
Usage: in=0 read=0 write=0 uncached=0 out=0 latency=654ms

Customer 4: ولو ينفع بعد الضهر
Tia: None
Usage: in=0 read=0 write=0 uncached=0 out=0 latency=608ms

Customer 5: جلسة الهيدرافيشل بكام؟
Tia: جلسة هيدرافيشل سعرها 1800 جنيه.
Usage: in=6160 read=5353 write=0 uncached=807 out=208 latency=6160ms

DB verification:
{
  "ownership": {
    "before_takeover": {
      "conversation_id": "4c1503a5-c0d2-4ff2-a8e6-d85574beb754",
      "owner_type": "ai",
      "status": "open",
      "assigned_user_id": null,
      "ownership_epoch": "2026-09-26T01:20:55.665975+00:00",
      "active_handoff_id": null,
      "active_handoff_status": null
    },
    "human_owned": {
      "conversation_id": "4c1503a5-c0d2-4ff2-a8e6-d85574beb754",
      "owner_type": "human",
      "status": "pending",
      "assigned_user_id": "511d5ace-5587-40d7-9312-39adc1cacd73",
      "ownership_epoch": "2026-09-26T01:21:03.708918+00:00",
      "active_handoff_id": "bb6c0e9e-504d-47ea-babe-d78f69ad24ef",
      "active_handoff_status": "claimed"
    },
    "staff_message_id": "ccb60083-233a-4d80-863b-75fe35702792",
    "staff_message": "أنا معاك من الريسبشن."
  },
  "human_turns_silent": true,
  "handback": {
    "conversation_id": "4c1503a5-c0d2-4ff2-a8e6-d85574beb754",
    "owner_type": "ai",
    "status": "open",
    "assigned_user_id": null,
    "ownership_epoch": "2026-09-26T01:21:07.390088+00:00",
    "active_handoff_id": null,
    "active_handoff_status": null
  },
  "db_delta": {
    "appointments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [
        "bb6c0e9e-504d-47ea-babe-d78f69ad24ef"
      ],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": [
    {
      "status": "claimed",
      "category": "other",
      "priority": "normal",
      "source": "staff"
    },
    {
      "status": "claimed",
      "category": "other",
      "priority": "normal",
      "source": "staff"
    },
    {
      "status": "claimed",
      "category": "other",
      "priority": "normal",
      "source": "staff"
    }
  ]
}
Deterministic findings: none; manual review still required.

## b4_07_package_reschedule_cancel_chain

Category: package_lifecycle
Purpose: Exercise one package reservation through booking, reschedule, and a cancellation request without double consume/refund.
Review status: PENDING_MANUAL_REVIEW
Expected: Package identity stays single through reschedule; cancellation either follows the current staff-handoff policy without mutation or releases exactly once if directly allowed.

Customer 1: احجزيلي PRP للبشرة من الباكدج يوم 2026-09-27 الساعة 16:00 مع مها
Tia: تم حجز جلسة PRP للبشرة يوم 27 سبتمبر الساعة 4:00 مساءً مع د. مها باستخدام الباكدج الموجود.
Usage: in=7687 read=5353 write=1572 uncached=762 out=328 latency=8722ms

Customer 2: غيريه ليوم 2026-10-02 الساعة 14:00
Tia: تم تغيير موعد جلسة PRP للبشرة ليوم 2 أكتوبر الساعة 2:00 مساءً مع مها، باستخدام الباكدج الموجود.
Usage: in=8270 read=5353 write=1996 uncached=921 out=576 latency=11986ms

Customer 3: تمام، الغيه خلاص
Tia: حاضر، إلغاء الموعد المدفوع محتاج يتم عن طريق الاستقبال. هيتواصلوا معاكي لإتمام الإلغاء.
Usage: in=7951 read=5353 write=1733 uncached=865 out=463 latency=8929ms

DB verification:
{
  "package_id": "9284758a-382c-4a63-9b11-1dd08aecd31b",
  "original_id": "01672dfb-9a10-467d-9d8a-3c9627a9a9a5",
  "replacement_after": [
    {
      "id": "201175ce-ca22-4973-9886-7cb51b533204",
      "status": "confirmed",
      "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
      "doctor_id": "73838381-f620-5acb-a70c-d1c911dee1dd",
      "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
      "start_at": "2026-10-02T11:00:00+00:00",
      "billing_context": "package_prepaid",
      "payment_status": "paid",
      "amount_paid_minor": null,
      "laser_device_key": null,
      "laser_device_name": null,
      "patient_package_id": "9284758a-382c-4a63-9b11-1dd08aecd31b",
      "rescheduled_from_appointment_id": "01672dfb-9a10-467d-9d8a-3c9627a9a9a5"
    }
  ],
  "package_after": {
    "id": "9284758a-382c-4a63-9b11-1dd08aecd31b",
    "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
    "name": "Batch4 lifecycle chain",
    "status": "active",
    "remaining": 1
  },
  "usages": [
    {
      "id": "2d9f34ea-b198-4c50-8529-19629ac8d6d6",
      "patient_package_id": "9284758a-382c-4a63-9b11-1dd08aecd31b",
      "appointment_id": "201175ce-ca22-4973-9886-7cb51b533204",
      "sessions_used": 1,
      "status": "reserved"
    }
  ],
  "canonical_financial_handoff": false,
  "direct_safe_cancel": false,
  "db_delta": {
    "appointments": {
      "created": [
        "01672dfb-9a10-467d-9d8a-3c9627a9a9a5",
        "201175ce-ca22-4973-9886-7cb51b533204"
      ],
      "removed": [],
      "changed": []
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": [
        "9284758a-382c-4a63-9b11-1dd08aecd31b"
      ]
    },
    "package_usages": {
      "created": [
        "2d9f34ea-b198-4c50-8529-19629ac8d6d6"
      ],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [
        "201885a7-9ec3-4456-a974-7b0cafc3d9fa"
      ],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": [
    {
      "status": "pending",
      "category": "other",
      "priority": "normal",
      "source": "ai"
    }
  ]
}
Deterministic findings:
- P1: Package reservation lifecycle double-mutated or lost identity — 

## b4_08_package_then_nonpackage_service

Category: package_lifecycle
Purpose: An existing package may cover Service A but must never leak onto a later Service B booking.
Review status: PENDING_MANUAL_REVIEW
Expected: Only the eligible PRP booking consumes the package; Hydrafacial remains standard with no Agent financial settlement.

Customer 1: احجزيلي PRP للبشرة من الباكدج يوم 2026-09-27 الساعة 16:00 مع مها
Tia: تم حجز جلسة PRP للبشرة يوم 27 سبتمبر الساعة 4:00 مساءً مع د. مها، باستخدام الباكدج الموجود.
Usage: in=7687 read=5353 write=1572 uncached=762 out=311 latency=9322ms

Customer 2: وكمان احجزيلي هيدرافيشل يوم 2026-09-28 الساعة 10:00 مع مريم حسن
Tia: تم حجز جلسة هيدرافيشل يوم 28 سبتمبر الساعة 10:00 صباحًا مع مريم حسن.
Usage: in=7915 read=5353 write=1629 uncached=933 out=350 latency=11837ms

DB verification:
{
  "package_id": "e76f9f24-2e81-4aa4-aa0a-b428e8a29de1",
  "created": [
    {
      "id": "c09e5d92-fd2a-44a9-bfb0-daed2edfdfd4",
      "status": "confirmed",
      "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
      "doctor_id": "73838381-f620-5acb-a70c-d1c911dee1dd",
      "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
      "start_at": "2026-09-27T13:00:00+00:00",
      "billing_context": "package_prepaid",
      "payment_status": "paid",
      "amount_paid_minor": null,
      "laser_device_key": null,
      "laser_device_name": null,
      "patient_package_id": "e76f9f24-2e81-4aa4-aa0a-b428e8a29de1",
      "rescheduled_from_appointment_id": null
    },
    {
      "id": "17b44036-5c86-4407-8cc7-724648e41bf2",
      "status": "confirmed",
      "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
      "doctor_id": "d18b8596-9342-57d9-a03d-6ef674a6f5e0",
      "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
      "start_at": "2026-09-28T07:00:00+00:00",
      "billing_context": "standard",
      "payment_status": "unknown",
      "amount_paid_minor": null,
      "laser_device_key": null,
      "laser_device_name": null,
      "patient_package_id": null,
      "rescheduled_from_appointment_id": null
    }
  ],
  "usages": [
    {
      "id": "ef58d08b-2e0d-45de-a66f-b991a87a47f8",
      "patient_package_id": "e76f9f24-2e81-4aa4-aa0a-b428e8a29de1",
      "appointment_id": "c09e5d92-fd2a-44a9-bfb0-daed2edfdfd4",
      "sessions_used": 1,
      "status": "reserved"
    }
  ],
  "db_delta": {
    "appointments": {
      "created": [
        "17b44036-5c86-4407-8cc7-724648e41bf2",
        "c09e5d92-fd2a-44a9-bfb0-daed2edfdfd4"
      ],
      "removed": [],
      "changed": []
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": [
        "e76f9f24-2e81-4aa4-aa0a-b428e8a29de1"
      ]
    },
    "package_usages": {
      "created": [
        "ef58d08b-2e0d-45de-a66f-b991a87a47f8"
      ],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## b4_09_exhausted_package_after_gap

Category: package_lifecycle
Purpose: Canonical zero balance must beat a stale historical conversation that claimed one package session remained.
Review status: PENDING_MANUAL_REVIEW
Expected: DB truth wins: no package-backed booking is created when canonical remaining sessions are zero.

Customer 1: احجزيلي PRP للبشرة من الباكدج يوم 2026-09-27 الساعة 16:00 مع مها
Tia: الميعاد متاح يوم 27 سبتمبر الساعة 4:00 مساءً مع مها، لكن للأسف مفيش باكدج ساري ينفع لجلسة PRP للبشرة في التاريخ ده. سعر الجلسة 2000 جنيه. تحبي أحجزه بالسعر العادي؟
Usage: in=7790 read=5353 write=1640 uncached=797 out=450 latency=10908ms

DB verification:
{
  "package_id": "e5fa269d-9556-4bc5-ab0a-acf7c2bbad82",
  "package_after": {
    "id": "e5fa269d-9556-4bc5-ab0a-acf7c2bbad82",
    "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
    "name": "Batch4 exhausted canonical",
    "status": "active",
    "remaining": 0
  },
  "created": [],
  "stale_claim": 1,
  "db_delta": {
    "appointments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## b4_10_two_appointments_one_package

Category: concurrent_lifecycles
Purpose: Two upcoming appointments plus an unrelated package must not widen lifecycle scope.
Review status: PENDING_MANUAL_REVIEW
Expected: Only the laser appointment changes; the skin appointment and unrelated package remain untouched.

Customer 1: غيري ميعاد الليزر وخلي جلسة البشرة زي ما هي، خلي الليزر يوم 2026-10-02 الساعة 14:00
Tia: الساعة ٢:٠٠ ظهرًا يوم ٢ أكتوبر مش متاحة لليزر. عندك اختيارين متاحين: ليزر إزالة الشعر – إبط مع أحمد محمود يوم ٣٠ سبتمبر الساعة ١٢:٠٠ ظهرًا، أو هيدرافيشل مع مريم حسن يوم ١ أكتوبر الساعة ١٠:٠٠ صباحًا. جلسة البشرة هتفضل زي ما هي؟
Usage: in=8130 read=5353 write=2012 uncached=765 out=436 latency=8049ms

DB verification:
{
  "laser_id": "94bf8069-5b84-4ef8-a961-c88c30a50d39",
  "skin_id": "1518fd34-5fa8-4f07-b828-c9d035c468dd",
  "package_id": "4609d45c-fcd1-47e2-b1a9-86b7741eaead",
  "replacements": [],
  "db_delta": {
    "appointments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings:
- P1: Concurrent lifecycle request changed the wrong appointment or package — 

## b4_11_cancel_one_then_modify_other

Category: concurrent_lifecycles
Purpose: After cancelling appointment A, a follow-up about the other appointment must bind to B rather than reuse the cancelled target.
Review status: PENDING_MANUAL_REVIEW
Expected: Laser is cancelled exactly once; the other appointment is then rescheduled without reviving the cancelled target.

Customer 1: الغِي ميعاد الليزر يوم 2026-09-30
Tia: تم إلغاء ميعاد ليزر إزالة الشعر للإبط يوم 30 سبتمبر 2026 الساعة 12:00 ظهرًا مع د. أحمد محمود في Tia Clinic.
Usage: in=7719 read=5353 write=1618 uncached=748 out=335 latency=8969ms

Customer 2: والتاني خليه يوم 2026-10-05 الساعة 11:15
Tia: تمام، تم نقل ميعاد الهيدرافيشل التاني ليوم 5 أكتوبر 2026 الساعة 11:15 صباحًا مع د. مريم حسن في Tia Clinic.
Usage: in=8116 read=5353 write=1942 uncached=821 out=502 latency=12340ms

DB verification:
{
  "cancelled_id": "1f148546-fc72-4403-95a3-71990f4ab88d",
  "other_id": "0b33ebaf-cedf-4bba-9b14-06d4a9c33948",
  "replacements": [
    {
      "id": "3aa5fb44-2812-4c00-b2ce-12d5642343d2",
      "status": "confirmed",
      "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
      "doctor_id": "d18b8596-9342-57d9-a03d-6ef674a6f5e0",
      "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
      "start_at": "2026-10-05T08:15:00+00:00",
      "billing_context": "standard",
      "payment_status": "unpaid",
      "amount_paid_minor": null,
      "laser_device_key": null,
      "laser_device_name": null,
      "patient_package_id": null,
      "rescheduled_from_appointment_id": "0b33ebaf-cedf-4bba-9b14-06d4a9c33948"
    }
  ],
  "db_delta": {
    "appointments": {
      "created": [
        "3aa5fb44-2812-4c00-b2ce-12d5642343d2"
      ],
      "removed": [],
      "changed": [
        "0b33ebaf-cedf-4bba-9b14-06d4a9c33948",
        "1f148546-fc72-4403-95a3-71990f4ab88d"
      ]
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## b4_12_same_service_different_dates_devices

Category: concurrent_lifecycles
Purpose: Date plus device must deterministically identify one of two same-service laser appointments.
Review status: PENDING_MANUAL_REVIEW
Expected: Only the Prime Lase appointment on the referenced date is rescheduled; Candela remains untouched.

Customer 1: غيري ميعاد الليزر بتاع Prime Lase يوم 2026-10-02 وخليه يوم 2026-10-05 الساعة 12:00
Tia: تم تغيير ميعاد جلسة ليزر إزالة الشعر للإبط من يوم 2 أكتوبر إلى يوم 5 أكتوبر الساعة 12:00 ظهرًا مع د. أحمد محمود على جهاز Prime Lase في Tia Clinic.
Usage: in=8074 read=5353 write=1953 uncached=768 out=417 latency=11929ms

DB verification:
{
  "candela_id": "60d9af73-a4d4-44b5-9b63-c873f1150fce",
  "prime_id": "d1e33eec-8f3b-43d1-af28-74c129d20287",
  "replacements": [
    {
      "id": "cf86e658-d8b7-4f90-af4f-93ada6b052a7",
      "status": "confirmed",
      "service_id": "ff83c8db-6e9a-5b5b-9e5b-b8d89692d28e",
      "doctor_id": "99902579-0e39-5df6-8f01-633b1ea859ef",
      "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
      "start_at": "2026-10-05T09:00:00+00:00",
      "billing_context": "standard",
      "payment_status": "unpaid",
      "amount_paid_minor": null,
      "laser_device_key": "prime_lase",
      "laser_device_name": "Prime Lase",
      "patient_package_id": null,
      "rescheduled_from_appointment_id": "d1e33eec-8f3b-43d1-af28-74c129d20287"
    }
  ],
  "db_delta": {
    "appointments": {
      "created": [
        "cf86e658-d8b7-4f90-af4f-93ada6b052a7"
      ],
      "removed": [],
      "changed": [
        "d1e33eec-8f3b-43d1-af28-74c129d20287"
      ]
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## b4_13_price_availability_existing_package

Category: multi_intent
Purpose: One informational turn combines canonical price, existing-package eligibility, and availability without authorizing payment or booking.
Review status: PENDING_MANUAL_REVIEW
Expected: Price, package eligibility, and availability are grounded in verified reads with zero booking/payment/Pulse mutation.

Customer 1: جلسة الـPRP للبشرة بكام، وعندي باكدج تنفع لها؟ ولو تنفع في ميعاد يوم 2026-09-29؟
Tia: جلسة الـPRP للبشرة بـ2000 جنيه. عندك باكدج فعال باسم Batch4 compound info، والمتبقي فيه جلستين، لكن مش موضح إنه ينفع لجلسات الـPRP. يوم 29 سبتمبر فيه مواعيد متاحة مع د. نور علي من 3 لـ9 مساءً، بإجمالي 25 اختيار متاح.
Usage: in=7704 read=5353 write=1583 uncached=768 out=745 latency=11979ms

DB verification:
{
  "package_id": "0cdd0e9c-5256-49e0-9e94-2160f3aed9d2",
  "verified_reads": [
    "availability",
    "customer_packages",
    "service_catalog"
  ],
  "operations": [
    "availability",
    "package_info",
    "pricing"
  ],
  "query_date": "2026-09-29",
  "db_delta": {
    "appointments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## b4_14_change_service_after_availability

Category: multi_intent
Purpose: Changing service after availability was already found must invalidate the old service assumptions and revalidate the new service.
Review status: PENDING_MANUAL_REVIEW
Expected: Hydrafacial availability is not reused as PRP availability; the PRP service is re-read/revalidated and no booking occurs yet.

Customer 1: عايزة أحجز هيدرافيشل يوم 2026-09-28
Tia: متاح هيدرافيشل يوم 28 سبتمبر مع د. أحمد محمود من 12:00 ظهرًا لـ5:00 مساءً، ومن 6:15 لـ9:00 مساءً؛ ومع د. عمر خليل من 2:00 لـ3:30 مساءً، ومن 5:15 لـ9:00 مساءً؛ ومع د. مريم حسن من 10:00 صباحًا لـ5:00 مساءً؛ ومع د. هالة مصطفى من 11:15 صباحًا لـ6:00 مساءً. السعر 1800 أو 2000 جنيه. اختاري المعاد والطبيب المناسبين للحجز.
Usage: in=7870 read=5353 write=1766 uncached=751 out=316 latency=7817ms

Customer 2: لا خليها PRP للبشرة
Tia: تمام، متاح PRP للبشرة يوم 28 سبتمبر مع د. هالة مصطفى من 11:15 صباحًا لـ6:00 مساءً. السعر 2000 جنيه. اختاري المعاد المناسب للحجز.
Usage: in=14664 read=5353 write=1569 uncached=7742 out=374 latency=9825ms

DB verification:
{
  "hydrafacial_service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
  "prp_service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
  "common_day": "2026-09-28",
  "changed_turn_operations": [
    {
      "type": "continue_active",
      "entities": {
        "service": {
          "text": "PRP للبشرة",
          "ref": "S1",
          "candidate_refs": [],
          "candidate_mode": "ambiguous"
        },
        "doctor": null,
        "device": null,
        "appointment": null,
        "package": null,
        "date": null,
        "time": null,
        "package_sessions": null,
        "pulse_count": null,
        "marketing_consent": null,
        "follow_up_at_local": null
      },
      "source_appointment": null,
      "selection": null,
      "package_usage": "unspecified",
      "requested_service_details": [],
      "requested_pulse_details": [],
      "financial_ownership": "none",
      "execution_intent": "execute",
      "continues_previous": false,
      "continuation_condition": "always"
    }
  ],
  "active_task_after_change": {
    "task_type": "booking",
    "status": "awaiting_choice",
    "write_authorization": {
      "operation": "booking",
      "authorized": true,
      "source_turn_id": "019a1349-cefc-4fe1-90c5-dfc94cf5c204",
      "granted_at": "2026-09-26T04:24:20.998531+03:00"
    },
    "constraints": {
      "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
      "doctor_id": null,
      "device_key": null,
      "date": {
        "mode": "exact",
        "start_date": "2026-09-28",
        "end_date": null
      },
      "time": null,
      "package_usage": "unspecified",
      "pulse_usage": "unspecified"
    },
    "derived": {
      "availability_snapshot_id": "04288669-d3ea-4c42-bb0c-d1ee0b960606:0:4",
      "selected_slot_ref": null,
      "selected_package_id": null,
      "package_validated": false,
      "doctor_compatible": null,
      "device_compatible": null
    },
    "option_snapshot": {
      "snapshot_id": "04288669-d3ea-4c42-bb0c-d1ee0b960606:0:4",
      "purpose": "booking_slot",
      "lifecycle_action": null,
      "task_version": 4,
      "created_at": "2026-09-26T04:24:29.672858+03:00",
      "expires_at": "2026-09-26T04:39:29.672858+03:00",
      "options": [
        {
          "ref": "slot-1",
          "label": "11:15 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T08:15:00+00:00",
            "start_local": "2026-09-28T11:15:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "11:15",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-2",
          "label": "11:30 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T08:30:00+00:00",
            "start_local": "2026-09-28T11:30:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "11:30",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-3",
          "label": "11:45 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T08:45:00+00:00",
            "start_local": "2026-09-28T11:45:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "11:45",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-4",
          "label": "12:00 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T09:00:00+00:00",
            "start_local": "2026-09-28T12:00:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "12:00",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-5",
          "label": "12:15 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T09:15:00+00:00",
            "start_local": "2026-09-28T12:15:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "12:15",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-6",
          "label": "12:30 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T09:30:00+00:00",
            "start_local": "2026-09-28T12:30:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "12:30",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-7",
          "label": "12:45 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T09:45:00+00:00",
            "start_local": "2026-09-28T12:45:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "12:45",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-8",
          "label": "13:00 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T10:00:00+00:00",
            "start_local": "2026-09-28T13:00:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "13:00",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-9",
          "label": "13:15 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T10:15:00+00:00",
            "start_local": "2026-09-28T13:15:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "13:15",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-10",
          "label": "13:30 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T10:30:00+00:00",
            "start_local": "2026-09-28T13:30:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "13:30",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-11",
          "label": "13:45 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T10:45:00+00:00",
            "start_local": "2026-09-28T13:45:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "13:45",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-12",
          "label": "14:00 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T11:00:00+00:00",
            "start_local": "2026-09-28T14:00:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "14:00",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-13",
          "label": "14:15 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T11:15:00+00:00",
            "start_local": "2026-09-28T14:15:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "14:15",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-14",
          "label": "14:30 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T11:30:00+00:00",
            "start_local": "2026-09-28T14:30:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "14:30",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-15",
          "label": "14:45 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T11:45:00+00:00",
            "start_local": "2026-09-28T14:45:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "14:45",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-16",
          "label": "15:00 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T12:00:00+00:00",
            "start_local": "2026-09-28T15:00:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "15:00",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-17",
          "label": "15:15 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T12:15:00+00:00",
            "start_local": "2026-09-28T15:15:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "15:15",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-18",
          "label": "15:30 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T12:30:00+00:00",
            "start_local": "2026-09-28T15:30:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "15:30",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-19",
          "label": "15:45 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T12:45:00+00:00",
            "start_local": "2026-09-28T15:45:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "15:45",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-20",
          "label": "16:00 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T13:00:00+00:00",
            "start_local": "2026-09-28T16:00:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "16:00",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-21",
          "label": "16:15 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T13:15:00+00:00",
            "start_local": "2026-09-28T16:15:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "16:15",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-22",
          "label": "16:30 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T13:30:00+00:00",
            "start_local": "2026-09-28T16:30:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "16:30",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-23",
          "label": "16:45 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T13:45:00+00:00",
            "start_local": "2026-09-28T16:45:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "16:45",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-24",
          "label": "17:00 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T14:00:00+00:00",
            "start_local": "2026-09-28T17:00:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "17:00",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-25",
          "label": "17:15 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T14:15:00+00:00",
            "start_local": "2026-09-28T17:15:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "17:15",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-26",
          "label": "17:30 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T14:30:00+00:00",
            "start_local": "2026-09-28T17:30:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "17:30",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-27",
          "label": "17:45 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T14:45:00+00:00",
            "start_local": "2026-09-28T17:45:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "17:45",
            "package_usage": "unspecified"
          }
        },
        {
          "ref": "slot-28",
          "label": "18:00 · هالة مصطفى",
          "payload": {
            "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
            "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
            "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
            "start_at": "2026-09-28T15:00:00+00:00",
            "start_local": "2026-09-28T18:00:00+03:00",
            "doctor_name": "هالة مصطفى",
            "service_name": "PRP للبشرة",
            "start_time_24h": "18:00",
            "package_usage": "unspecified"
          }
        }
      ]
    },
    "version": 4
  },
  "prp_slots_on_day": 28,
  "db_delta": {
    "appointments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## b4_15_incremental_doctor_date_service_corrections

Category: multi_intent
Purpose: Natural corrections across date, doctor, and service must converge to only the latest explicit values.
Review status: PENDING_MANUAL_REVIEW
Expected: Exactly one final Hydrafacial booking reflects the latest date, doctor, service, and time; superseded values do not leak.

Customer 1: عايزة أحجز PRP للبشرة
Tia: تمام، تحبي الحجز يكون يوم إيه؟
Usage: in=7359 read=5353 write=1263 uncached=743 out=208 latency=6599ms

Customer 2: يوم 2026-10-02
Tia: متاح يوم 2 أكتوبر 2026 لحجز PRP للبشرة:
• د. مها: من 2:00 ظهرًا لحد 9:00 مساءً
• د. نور علي: من 3:00 عصرًا لحد 9:00 مساءً
السعر 2000 جنيه. تحبي أي دكتورة وميعاد؟
Usage: in=7681 read=5353 write=1505 uncached=823 out=290 latency=8447ms

Customer 3: لا خليه يوم 2026-09-28
Tia: متاح يوم 28 سبتمبر 2026 لحجز PRP للبشرة مع د. هالة مصطفى من 11:15 صباحًا لحد 6:00 مساءً، والسعر 2000 جنيه. تحبي تختاري ميعاد؟
Usage: in=10890 read=5353 write=1535 uncached=4002 out=371 latency=8811ms

Customer 4: مع مها
Tia: للأسف مفيش مواعيد متاحة لـ PRP للبشرة يوم 28 سبتمبر 2026 مع د. مها.
Usage: in=9595 read=5353 write=1517 uncached=2725 out=480 latency=9528ms

Customer 5: لا مع هالة مصطفى
Tia: تمام، متاح يوم 28 سبتمبر 2026 مع د. هالة مصطفى من 11:15 صباحًا لحد 6:00 مساءً، والسعر 2000 جنيه. اختاري الميعاد المناسب ليكي.
Usage: in=8047 read=5353 write=1643 uncached=1051 out=440 latency=9604ms

Customer 6: بدل PRP للبشرة خليها هيدرافيشل
Tia: تمام، هنخليها هيدرافيشل بدل PRP للبشرة. متاح يوم 28 سبتمبر 2026 مع د. هالة مصطفى من 11:15 صباحًا لحد 6:00 مساءً، والسعر 2000 جنيه. اختاري الميعاد المناسب ليكي.
Usage: in=9814 read=5353 write=1685 uncached=2776 out=430 latency=10170ms

Customer 7: الساعة 11:15
Tia: تم حجز الهيدرافيشل يوم 28 سبتمبر 2026 الساعة 11:15 صباحًا مع د. هالة مصطفى.
Usage: in=12241 read=5353 write=4095 uncached=2793 out=401 latency=10601ms

DB verification:
{
  "initial_date": "2026-10-02",
  "final_date": "2026-09-28",
  "initial_doctor_id": "73838381-f620-5acb-a70c-d1c911dee1dd",
  "final_doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
  "initial_service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
  "final_service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
  "final_time": "11:15",
  "created": [
    {
      "id": "4c3c655a-7562-4570-ae11-f243c934d238",
      "status": "confirmed",
      "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
      "doctor_id": "e4dcaadf-822d-5f5a-9df7-6207243e9854",
      "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
      "start_at": "2026-09-28T08:15:00+00:00",
      "billing_context": "standard",
      "payment_status": "unknown",
      "amount_paid_minor": null,
      "laser_device_key": null,
      "laser_device_name": null,
      "patient_package_id": null,
      "rescheduled_from_appointment_id": null
    }
  ],
  "db_delta": {
    "appointments": {
      "created": [
        "4c3c655a-7562-4570-ae11-f243c934d238"
      ],
      "removed": [],
      "changed": []
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## b4_16_repeat_reschedule_confirmation

Category: idempotency
Purpose: A conversational acknowledgment after a successful reschedule must not execute a second reschedule.
Review status: PENDING_MANUAL_REVIEW
Expected: The first turn reschedules once; the follow-up is acknowledgment-only with no additional appointment write.

Customer 1: غيري ميعاد هيدرافيشل يوم 2026-09-29 وخليه يوم 2026-10-01 الساعة 14:00
Tia: تم تغيير ميعاد الهيدرافيشل بنجاح ليوم 1 أكتوبر 2026 الساعة 2:00 ظهرًا مع عمر خليل في Tia Clinic. السعر 1800 جنيه، والحجز غير مدفوع حتى الآن.
Usage: in=8038 read=5353 write=1920 uncached=765 out=440 latency=10784ms

Customer 2: تمام كده خليها على الميعاد الجديد
Tia: تمام، الساعة 2:00 يوم 1 أكتوبر متاحة مع د. سارة عادل أو د. يوسف سمير. تحبي أحجز مع مين؟
Usage: in=7822 read=5353 write=1634 uncached=835 out=635 latency=10957ms

DB verification:
{
  "source_id": "1cc4959f-5519-4f25-9c91-12743c84b9ab",
  "replacements": [
    {
      "id": "a9b542c7-371b-477d-b802-a1f0d78d7970",
      "status": "confirmed",
      "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
      "doctor_id": "6dd310a2-9f33-568f-b2e0-dd5db0e476c6",
      "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
      "start_at": "2026-10-01T11:00:00+00:00",
      "billing_context": "standard",
      "payment_status": "unpaid",
      "amount_paid_minor": null,
      "laser_device_key": null,
      "laser_device_name": null,
      "patient_package_id": null,
      "rescheduled_from_appointment_id": "1cc4959f-5519-4f25-9c91-12743c84b9ab"
    }
  ],
  "ack_write_attempted": false,
  "db_delta": {
    "appointments": {
      "created": [
        "a9b542c7-371b-477d-b802-a1f0d78d7970"
      ],
      "removed": [],
      "changed": [
        "1cc4959f-5519-4f25-9c91-12743c84b9ab"
      ]
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "package_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## b4_17_repeat_package_booking_confirmation

Category: idempotency
Purpose: Repeating conversational confirmation after a successful package booking must not duplicate the appointment or PackageUsage.
Review status: PENDING_MANUAL_REVIEW
Expected: Exactly one package-backed appointment and one reserved usage remain after the repeated confirmation.

Customer 1: احجزيلي PRP للبشرة من الباكدج يوم 2026-09-27 الساعة 16:00 مع مها
Tia: تم حجز جلسة PRP للبشرة يوم 27 سبتمبر الساعة 4:00 مساءً مع د. مها، باستخدام الباكدج الموجود.
Usage: in=7689 read=5353 write=1574 uncached=762 out=266 latency=7774ms

Customer 2: اه تمام احجزيه كده
Tia: تمام، الحجز ده اتعمل بالفعل بنفس التفاصيل.
Usage: in=7613 read=5353 write=1346 uncached=914 out=354 latency=7290ms

DB verification:
{
  "package_id": "3569fb87-fe80-4837-982e-3841186af84b",
  "created": [
    {
      "id": "799ddc35-1d1c-4693-ad09-b6b486342c72",
      "status": "confirmed",
      "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
      "doctor_id": "73838381-f620-5acb-a70c-d1c911dee1dd",
      "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
      "start_at": "2026-09-27T13:00:00+00:00",
      "billing_context": "package_prepaid",
      "payment_status": "paid",
      "amount_paid_minor": null,
      "laser_device_key": null,
      "laser_device_name": null,
      "patient_package_id": "3569fb87-fe80-4837-982e-3841186af84b",
      "rescheduled_from_appointment_id": null
    }
  ],
  "usages": [
    {
      "id": "b6f58e05-b9f5-4917-b72f-cc6fab94a733",
      "patient_package_id": "3569fb87-fe80-4837-982e-3841186af84b",
      "appointment_id": "799ddc35-1d1c-4693-ad09-b6b486342c72",
      "sessions_used": 1,
      "status": "reserved"
    }
  ],
  "package_after": {
    "id": "3569fb87-fe80-4837-982e-3841186af84b",
    "service_id": "abf2f14d-713d-543d-ad14-79837d909b5c",
    "name": "Batch4 idempotent package",
    "status": "active",
    "remaining": 1
  },
  "ack_write_attempted": false,
  "db_delta": {
    "appointments": {
      "created": [
        "799ddc35-1d1c-4693-ad09-b6b486342c72"
      ],
      "removed": [],
      "changed": []
    },
    "packages": {
      "created": [],
      "removed": [],
      "changed": [
        "3569fb87-fe80-4837-982e-3841186af84b"
      ]
    },
    "package_usages": {
      "created": [
        "b6f58e05-b9f5-4917-b72f-cc6fab94a733"
      ],
      "removed": [],
      "changed": []
    },
    "pulse_packs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "payments": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_usages": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_settlements": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "handoffs": {
      "created": [],
      "removed": [],
      "changed": []
    },
    "pulse_balance_delta": {}
  },
  "handoffs": []
}
Deterministic findings: none; manual review still required.

## Batch summary

{
  "scenarios_run": 17,
  "pending_manual_review": 17,
  "infrastructure_failures": 0,
  "deterministic_P0": 0,
  "deterministic_P1": 2,
  "deterministic_P2": 0,
  "tokens": {
    "input_tokens": 289165,
    "output_tokens": 12931,
    "cached_tokens": 187355,
    "cache_write_tokens": 57460,
    "uncached_input_tokens": 44350,
    "total_tokens": 302096,
    "average_tokens_per_conversation": 17770.35,
    "median_tokens_per_conversation": 15722,
    "max_tokens": 68247,
    "max_scenario": "b4_15_incremental_doctor_date_service_corrections",
    "min_tokens": 7580,
    "min_scenario": "b4_03_completed_appointment_not_actionable"
  },
  "total_turns": 38,
  "total_llm_calls": 69,
  "interpreter_calls": 35,
  "responder_calls": 34,
  "stage_metrics": {
    "interpreter": {
      "calls": 35,
      "input_tokens": 231603,
      "cached_read_tokens": 187355,
      "cache_write_tokens": 0,
      "uncached_tokens": 44248,
      "output_tokens": 10303,
      "latency_ms": 137484,
      "retries": 0,
      "fallback_calls": 0
    },
    "responder": {
      "calls": 34,
      "input_tokens": 57562,
      "cached_read_tokens": 0,
      "cache_write_tokens": 57460,
      "uncached_tokens": 102,
      "output_tokens": 2628,
      "latency_ms": 65116,
      "retries": 0,
      "fallback_calls": 0
    },
    "all": {
      "calls": 69,
      "input_tokens": 289165,
      "cached_read_tokens": 187355,
      "cache_write_tokens": 57460,
      "uncached_tokens": 44350,
      "output_tokens": 12931,
      "latency_ms": 202600,
      "retries": 0,
      "fallback_calls": 0
    },
    "turn_latency_ms": 322905
  },
  "cost": {
    "actual_usd": 0.0424993,
    "without_explicit_cache_usd": 0.0733502,
    "saving_usd": 0.0308509,
    "saving_percent": 42.06
  },
  "stopped_for_deterministic_p0": false
}