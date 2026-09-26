# Tia Agent Evaluation — Batch 05 Raw Baseline

- Batch runtime base SHA: 54c2055767761d5e8bc753e0872117812f9e8c8e
- Harness SHA: 54c2055767761d5e8bc753e0872117812f9e8c8e
- Scenario version: batch5-v1
- Model: gpt-5.6-luna
- Reasoning: low
- Scenarios executed: 15

Raw deterministic findings are guards; final verdict requires manual DB/write/response review.

## b5_01_same_name_different_patients

Category: patient_identity
Purpose: Ambiguous same-name third-party patients must never be guessed from customer text.
Review status: PENDING_MANUAL_REVIEW
Expected: No cross-patient read-derived mutation; clarify or stay scoped to the verified current customer.

Customer 1: غيري ميعاد محمد أحمد
Tia: ممكن تحدديلي التاريخ الجديد اللي حابة تنقلي له ميعاد محمد أحمد؟
Usage: in=7372 read=5353 write=1279 uncached=740 out=296 latency=9802ms

DB verification:
{
  "ambiguous_patient_ids": [
    "300c6f5e-9930-47e6-b508-a77466cb5a33",
    "1a12d7f0-6258-4607-a48a-d73921c4448d"
  ],
  "ambiguous_appointment_ids": [
    "27b9ddd6-670d-482f-b6c3-4460d2d4e206",
    "7d09327c-4f2b-41ed-852f-8ea9a1fa5665"
  ],
  "other_before": {
    "300c6f5e-9930-47e6-b508-a77466cb5a33": [
      {
        "id": "27b9ddd6-670d-482f-b6c3-4460d2d4e206",
        "status": "confirmed",
        "start_at": "2026-09-29T07:00:00+00:00",
        "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
        "doctor_id": "6dd310a2-9f33-568f-b2e0-dd5db0e476c6",
        "laser_device_key": null,
        "rescheduled_from_appointment_id": null
      }
    ],
    "1a12d7f0-6258-4607-a48a-d73921c4448d": [
      {
        "id": "7d09327c-4f2b-41ed-852f-8ea9a1fa5665",
        "status": "confirmed",
        "start_at": "2026-09-29T07:00:00+00:00",
        "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
        "doctor_id": "d18b8596-9342-57d9-a03d-6ef674a6f5e0",
        "laser_device_key": null,
        "rescheduled_from_appointment_id": null
      }
    ]
  },
  "other_after": {
    "300c6f5e-9930-47e6-b508-a77466cb5a33": [
      {
        "id": "27b9ddd6-670d-482f-b6c3-4460d2d4e206",
        "status": "confirmed",
        "start_at": "2026-09-29T07:00:00+00:00",
        "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
        "doctor_id": "6dd310a2-9f33-568f-b2e0-dd5db0e476c6",
        "laser_device_key": null,
        "rescheduled_from_appointment_id": null
      }
    ],
    "1a12d7f0-6258-4607-a48a-d73921c4448d": [
      {
        "id": "7d09327c-4f2b-41ed-852f-8ea9a1fa5665",
        "status": "confirmed",
        "start_at": "2026-09-29T07:00:00+00:00",
        "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
        "doctor_id": "d18b8596-9342-57d9-a03d-6ef674a6f5e0",
        "laser_device_key": null,
        "rescheduled_from_appointment_id": null
      }
    ]
  },
  "availability_dates": [
    "2026-09-29",
    "2026-09-29"
  ],
  "cross_patient_mutation": false,
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

## b5_02_phone_beats_ambiguous_name

Category: patient_identity
Purpose: Verified current-customer identity must beat an ambiguous duplicated name.
Review status: PENDING_MANUAL_REVIEW
Expected: Only the verified current customer's appointment is rescheduled; the same-name patient is untouched.

Customer 1: أنا محمد أحمد، غيري ميعادي وخليه يوم 2026-10-01 الساعة 14:00
Tia: تم تغيير ميعادك لهيدرافيشل ليوم 1 أكتوبر 2026 الساعة 2:00 ظهرًا مع عمر خليل في Tia Clinic. السعر 1800 جنيه والدفع لم يتم بعد.
Usage: in=8003 read=5353 write=1892 uncached=758 out=261 latency=10036ms

DB verification:
{
  "current_patient_id": "576421f5-b895-587a-a3c3-196f183ccda2",
  "current_phone": "+201010000012",
  "other_patient_id": "3ffda92f-a5f9-492a-b114-9257ffa4df8b",
  "other_appointment_id": "eb34b48d-b255-48c7-8aff-d1b7f8b47cad",
  "other_unchanged": true,
  "replacements": [
    {
      "id": "2138ed4a-b6dd-4363-a5fc-aceb868e8752",
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
      "rescheduled_from_appointment_id": "92dd38c7-a2c1-4e34-a856-67101c045b0a"
    }
  ],
  "db_delta": {
    "appointments": {
      "created": [
        "2138ed4a-b6dd-4363-a5fc-aceb868e8752"
      ],
      "removed": [],
      "changed": [
        "92dd38c7-a2c1-4e34-a856-67101c045b0a"
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

## b5_03_historical_name_not_current_identity

Category: patient_identity
Purpose: A stale historical patient name must not override the verified current customer.
Review status: PENDING_MANUAL_REVIEW
Expected: Canonical current identity wins; no cross-patient read/write occurs.

Customer 1: أنا سارة علي، خليه يوم 2026-10-01 الساعة 14:00
Tia: تمام، اتغيّر ميعادك ليوم 2026-10-01 الساعة 2:00 ظهرًا.
Usage: in=8055 read=5353 write=1918 uncached=784 out=398 latency=10288ms

DB verification:
{
  "current_patient_id": "576421f5-b895-587a-a3c3-196f183ccda2",
  "historical_name": "محمود حسن",
  "other_patient_id": "6249c1c1-9ca2-4c73-80f4-2e1113fdc7c3",
  "other_appointment_id": "1371da27-4c73-4843-8221-58d77f0dcbe5",
  "other_unchanged": true,
  "replacements": [
    {
      "id": "9a66d258-dba9-40a5-8da1-bf91732d96e0",
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
      "rescheduled_from_appointment_id": "0896e195-42d2-412a-b829-ce5ee9849bd5"
    }
  ],
  "db_delta": {
    "appointments": {
      "created": [
        "9a66d258-dba9-40a5-8da1-bf91732d96e0"
      ],
      "removed": [],
      "changed": [
        "0896e195-42d2-412a-b829-ce5ee9849bd5"
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

## b5_04_slot_becomes_unavailable

Category: changing_scheduling_truth
Purpose: A slot verified earlier must not remain writable after canonical availability changes.
Review status: PENDING_MANUAL_REVIEW
Expected: No double booking; write-time/canonical validation wins and the stale slot is reported unavailable.

Customer 1: هل هيدرافيشل يوم 2026-09-29 الساعة 10:00 مع عمر خليل متاح؟
Tia: أيوه، هيدرافيشل يوم 29 سبتمبر الساعة 10:00 صباحًا مع عمر خليل متاح. السعر 1800 جنيه.
Usage: in=7555 read=5353 write=1443 uncached=759 out=269 latency=6168ms

Customer 2: تمام احجزيه
Tia: للأسف الموعد يوم 29 سبتمبر الساعة 10:00 صباحًا مش متاح، فمش هقدر أحجزه.
Usage: in=7767 read=5353 write=1423 uncached=991 out=465 latency=8911ms

DB verification:
{
  "requested_start_at": "2026-09-29T07:00:00+00:00",
  "competing_appointment_id": "b4b4a819-e02a-46d0-9272-26d6ed46ccc8",
  "created_for_customer": [],
  "booking_turn_reads": [
    "availability"
  ],
  "booking_write_result": null,
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

## b5_05_doctor_schedule_changes_between_turns

Category: changing_scheduling_truth
Purpose: Doctor schedule changes after an earlier availability answer must invalidate that answer.
Review status: PENDING_MANUAL_REVIEW
Expected: Fresh canonical doctor availability is checked before write; no stale-slot booking occurs.

Customer 1: هل هيدرافيشل يوم 2026-09-28 الساعة 12:00 مع أحمد محمود متاح؟
Tia: أيوه، هيدرافيشل متاح يوم 28 سبتمبر 2026 الساعة 12:00 مع أحمد محمود. السعر 1800 جنيه.
Usage: in=7553 read=5353 write=1442 uncached=758 out=271 latency=6286ms

Customer 2: تمام احجزيه
Tia: الساعة 12:00 يوم 28 سبتمبر مش متاحة، فمش هقدر أحجزها في الوقت ده.
Usage: in=7771 read=5353 write=1422 uncached=996 out=314 latency=9665ms

DB verification:
{
  "doctor_id": "99902579-0e39-5df6-8f01-633b1ea859ef",
  "requested_start_at": "2026-09-28T09:00:00+00:00",
  "working_hours_removed": 1,
  "booking_turn_reads": [
    "availability"
  ],
  "created_for_customer": [],
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

## b5_06_cancelled_externally_before_reschedule

Category: changing_scheduling_truth
Purpose: Externally cancelled appointments must not be resurrected by stale conversational reschedule state.
Review status: PENDING_MANUAL_REVIEW
Expected: Canonical cancelled state wins; no reschedule/revival write occurs.

Customer 1: ممكن أغير ميعادي؟
Tia: أكيد، ممكن نغيّر الميعاد. تحبي يكون في تاريخ إيه؟
Usage: in=7652 read=5353 write=1557 uncached=742 out=317 latency=6948ms

Customer 2: خليه يوم 2026-10-01 الساعة 14:00
Tia: الميعاد يوم 1 أكتوبر 2026 الساعة 2:00 ظهرًا متاح مع د. عمر خليل. تحبي أغيّر حجزك عليه؟
Usage: in=7698 read=5353 write=1495 uncached=850 out=548 latency=8918ms

DB verification:
{
  "source_id": "27ffef18-1fc1-4c4e-8aef-4df4c8f5441a",
  "external_status_before_customer_turn": "cancelled",
  "appointment_after": {
    "id": "27ffef18-1fc1-4c4e-8aef-4df4c8f5441a",
    "status": "cancelled",
    "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
    "doctor_id": "6dd310a2-9f33-568f-b2e0-dd5db0e476c6",
    "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
    "start_at": "2026-09-29T07:00:00+00:00",
    "billing_context": "standard",
    "payment_status": "unpaid",
    "amount_paid_minor": null,
    "laser_device_key": null,
    "laser_device_name": null,
    "patient_package_id": null,
    "rescheduled_from_appointment_id": null
  },
  "replacements": [],
  "second_turn_reads": [
    "appointments",
    "availability"
  ],
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

## b5_07_same_day_current_time_boundary

Category: changing_scheduling_truth
Purpose: Same-day booking must follow the current canonical notice rule, not a stale one-hour assumption.
Review status: PENDING_MANUAL_REVIEW
Expected: The earliest canonical same-day slot is bookable exactly when current business rules allow it.

Customer 1: احجزيلي هيدرافيشل النهارده 2026-09-26 الساعة 14:00 مع عمر خليل
Tia: تم حجز جلسة هيدرافيشل النهارده 26 سبتمبر 2026 الساعة 2:00 مساءً مع عمر خليل، بسعر 1800 جنيه.
Usage: in=7674 read=5353 write=1560 uncached=761 out=271 latency=9047ms

DB verification:
{
  "local_now": "2026-09-26T12:51:05.230786+03:00",
  "canonical_minimum_notice_minutes": 60,
  "requested_notice_minutes": 68,
  "requested_start_at": "2026-09-26T11:00:00+00:00",
  "created": [
    {
      "id": "ee033f61-9418-455a-84be-b1ce80d679ea",
      "status": "confirmed",
      "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
      "doctor_id": "6dd310a2-9f33-568f-b2e0-dd5db0e476c6",
      "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
      "start_at": "2026-09-26T11:00:00+00:00",
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
        "ee033f61-9418-455a-84be-b1ce80d679ea"
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

## 08_doctor_does_not_offer_service

Category: infrastructure
Purpose: Scenario execution failed before review.
Review status: INFRASTRUCTURE_FAILURE
Expected:

DB verification:
{}
Deterministic findings: none; manual review still required.

## b5_09_laser_requires_device

Category: compatibility
Purpose: A device-required laser service must resolve a compatible device canonically or clarify.
Review status: PENDING_MANUAL_REVIEW
Expected: No invented device; any booking uses a verified compatible device, otherwise the Agent clarifies.

Customer 1: احجزيلي ليزر إزالة الشعر - إبط يوم 2026-09-28 الساعة 12:00 مع أحمد محمود
Tia: الساعة 12:00 يوم 28 سبتمبر متاحة مع د. أحمد محمود بجهازين: Candela Gentle بسعر 550 جنيه، أو Prime Lase بسعر 650 جنيه. تحبي أحجزلك بأي جهاز؟
Usage: in=7670 read=5353 write=1556 uncached=761 out=291 latency=7656ms

DB verification:
{
  "service_id": "ff83c8db-6e9a-5b5b-9e5b-b8d89692d28e",
  "valid_device_keys": [
    "candela_gentle",
    "prime_lase"
  ],
  "created": [],
  "verified_reads": [
    "availability"
  ],
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

## 10_explicit_incompatible_device

Category: infrastructure
Purpose: Scenario execution failed before review.
Review status: INFRASTRUCTURE_FAILURE
Expected:

DB verification:
{}
Deterministic findings: none; manual review still required.

## b5_11_doctor_change_invalidates_availability

Category: compatibility
Purpose: Changing doctors must invalidate availability shown for the previous doctor.
Review status: PENDING_MANUAL_REVIEW
Expected: Doctor B availability is freshly verified; no Doctor A slot is reused.

Customer 1: عايزة أحجز هيدرافيشل يوم 2026-09-28 مع أحمد محمود، المواعيد إيه؟
Tia: متاح هيدرافيشل يوم 28 سبتمبر مع د. أحمد محمود من 12:00 ظهرًا لـ5:00 مساءً، وكمان من 6:15 لـ9:00 مساءً. السعر 1800 جنيه.
Usage: in=7597 read=5353 write=1483 uncached=761 out=253 latency=5685ms

Customer 2: لا خليها مع عمر خليل
Tia: تمام، متاح هيدرافيشل يوم 28 سبتمبر مع عمر خليل من 2:00 لـ3:30 ظهرًا، ومن 5:15 لـ9:00 مساءً. السعر 1800 جنيه.
Usage: in=7885 read=5353 write=1549 uncached=983 out=288 latency=6946ms

DB verification:
{
  "doctor_a_id": "99902579-0e39-5df6-8f01-633b1ea859ef",
  "doctor_b_id": "6dd310a2-9f33-568f-b2e0-dd5db0e476c6",
  "date": "2026-09-28",
  "doctor_a_unique_start": "2026-09-28T09:00:00+00:00",
  "doctor_b_slot_count": 23,
  "changed_turn_reads": [
    "availability"
  ],
  "created": [],
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

## b5_12_duplicate_booking_after_external_change

Category: stale_duplicate_safety
Purpose: A repeated confirmation after an external state change must consult canonical state instead of blindly acknowledging the old action.
Review status: PENDING_MANUAL_REVIEW
Expected: Recent-action context never masks the external canonical change; at most one active booking remains.

Customer 1: احجزيلي هيدرافيشل يوم 2026-09-29 الساعة 10:00 مع عمر خليل
Tia: تم حجز جلسة الهيدرافيشل يوم 29 سبتمبر 2026 الساعة 10:00 صباحًا مع عمر خليل، وسعر الجلسة 1800 جنيه.
Usage: in=7670 read=5353 write=1558 uncached=759 out=276 latency=7542ms

Customer 2: اه تمام احجزيه كده
Tia: فيه مواعيد متاحة مؤكدة، لكن تفاصيل الفترة مش متاحة للعرض هنا.
Usage: in=7897 read=5353 write=1627 uncached=917 out=385 latency=8535ms

DB verification:
{
  "externally_cancelled_appointment_id": "79b9d116-0cac-41af-b9fc-bebd2180efc3",
  "repeat_verified_reads": [
    "appointments",
    "availability"
  ],
  "repeat_write_attempted": true,
  "active_appointments_after": [
    {
      "id": "32009759-efaf-43ff-ab8c-47d6ef81becb",
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
        "32009759-efaf-43ff-ab8c-47d6ef81becb"
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

## b5_13_repeat_cancel_after_external_change

Category: stale_duplicate_safety
Purpose: Repeating cancellation after canonical state already changed must be non-destructive.
Review status: PENDING_MANUAL_REVIEW
Expected: No duplicate destructive cancellation; canonical cancelled state is respected.

Customer 1: الغيه
Tia: مش لاقية أي ميعاد هيدرافيشل مسجّل يوم 29 سبتمبر 2026. ممكن تبعتيلي الساعة أو تفاصيل أكتر عن الميعاد؟
Usage: in=7471 read=5353 write=1333 uncached=785 out=379 latency=7223ms

DB verification:
{
  "appointment_id": "2733339c-3a90-4741-8d49-b0c22bf0e00a",
  "appointment_after": {
    "id": "2733339c-3a90-4741-8d49-b0c22bf0e00a",
    "status": "cancelled",
    "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
    "doctor_id": "6dd310a2-9f33-568f-b2e0-dd5db0e476c6",
    "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
    "start_at": "2026-09-29T07:00:00+00:00",
    "billing_context": "standard",
    "payment_status": "unpaid",
    "amount_paid_minor": null,
    "laser_device_key": null,
    "laser_device_name": null,
    "patient_package_id": null,
    "rescheduled_from_appointment_id": null
  },
  "verified_reads": [
    "appointments"
  ],
  "write_attempted": false,
  "write_result": null,
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

## b5_14_availability_then_competing_laser_booking

Category: stale_duplicate_safety
Purpose: A competing device booking after availability read must defeat the stale write safely.
Review status: PENDING_MANUAL_REVIEW
Expected: No device double-booking and no false successful write after the competing booking.

Customer 1: هل ليزر إزالة الشعر - إبط يوم 2026-09-28 الساعة 12:00 مع أحمد محمود على Candela Gentle متاح؟
Tia: أيوه، الموعد متاح يوم 28 سبتمبر 2026 الساعة 12:00 ظهرًا مع أحمد محمود على جهاز Candela Gentle، وسعر الجلسة 650 جنيه.
Usage: in=7577 read=5353 write=1459 uncached=765 out=351 latency=7184ms

Customer 2: تمام احجزيه
Tia: للأسف، الموعد يوم 28 سبتمبر الساعة 12:00 مع أحمد محمود على جهاز Candela Gentle غير متاح، فمش هقدر أحجزه.
Usage: in=7852 read=5353 write=1440 uncached=1059 out=387 latency=8357ms

DB verification:
{
  "device_key": "candela_gentle",
  "requested_start_at": "2026-09-28T09:00:00+00:00",
  "competing_appointment_id": "ebef189c-c13f-4394-8cf9-8107b5fdc7b9",
  "confirm_reads": [
    "availability"
  ],
  "confirm_write_attempted": false,
  "confirm_write_result": null,
  "created_for_customer": [],
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

## b5_15_two_rapid_customer_turns

Category: stale_duplicate_safety
Purpose: Back-to-back booking then correction must converge to the latest legitimate intent without duplicate active appointments.
Review status: PENDING_MANUAL_REVIEW
Expected: Exactly one active appointment remains at the corrected time; no out-of-order stale write survives.

Customer 1: احجزيلي هيدرافيشل يوم 2026-09-28 الساعة 12:00 مع أحمد محمود
Tia: تم حجز جلسة هيدرافيشل يوم 28 سبتمبر 2026 الساعة 12:00 مع أحمد محمود. السعر 1800 جنيه.
Usage: in=7668 read=5353 write=1557 uncached=758 out=267 latency=8203ms

Customer 2: لا خليها الساعة 21:00
Tia: تمام، تم تعديل حجز الهيدرافيشل مع أحمد محمود ليوم 28 سبتمبر 2026 الساعة 21:00. السعر 1800 جنيه.
Usage: in=8252 read=5353 write=1990 uncached=909 out=553 latency=10879ms

DB verification:
{
  "conversation_id": "34339c92-81c7-4cea-9286-61431f6f4dc4",
  "first_requested_start": "2026-09-28T09:00:00+00:00",
  "second_requested_start": "2026-09-28T18:00:00+00:00",
  "turn_order": [
    1,
    2
  ],
  "active_appointments_after": [
    {
      "id": "3cb1a1f8-5b49-41c4-a25b-87254f5c8889",
      "status": "confirmed",
      "service_id": "8bcbaab6-775a-5d39-8f41-ececf3b90616",
      "doctor_id": "99902579-0e39-5df6-8f01-633b1ea859ef",
      "branch_id": "dc6c1238-9c5c-5251-a449-835881592b8b",
      "start_at": "2026-09-28T18:00:00+00:00",
      "billing_context": "standard",
      "payment_status": "unknown",
      "amount_paid_minor": null,
      "laser_device_key": null,
      "laser_device_name": null,
      "patient_package_id": null,
      "rescheduled_from_appointment_id": "77539597-3eb1-477a-97be-685c32ab0bea"
    }
  ],
  "correction_reads": [
    "appointments",
    "availability"
  ],
  "correction_write_result": "completed",
  "db_delta": {
    "appointments": {
      "created": [
        "3cb1a1f8-5b49-41c4-a25b-87254f5c8889",
        "77539597-3eb1-477a-97be-685c32ab0bea"
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

## Batch summary

{
  "scenarios_run": 15,
  "pending_manual_review": 13,
  "infrastructure_failures": 2,
  "deterministic_P0": 0,
  "deterministic_P1": 0,
  "deterministic_P2": 0,
  "tokens": {
    "input_tokens": 154639,
    "output_tokens": 6840,
    "cached_tokens": 107060,
    "cache_write_tokens": 30983,
    "uncached_input_tokens": 16596,
    "total_tokens": 161479,
    "average_tokens_per_conversation": 10765.27,
    "median_tokens_per_conversation": 8453,
    "max_tokens": 16740,
    "max_scenario": "b5_15_two_rapid_customer_turns",
    "min_tokens": 0,
    "min_scenario": "08_doctor_does_not_offer_service"
  },
  "total_turns": 20,
  "total_llm_calls": 40,
  "interpreter_calls": 20,
  "responder_calls": 20,
  "stage_metrics": {
    "interpreter": {
      "calls": 20,
      "input_tokens": 123596,
      "cached_read_tokens": 107060,
      "cache_write_tokens": 0,
      "uncached_tokens": 16536,
      "output_tokens": 5264,
      "latency_ms": 62159,
      "retries": 0,
      "fallback_calls": 0
    },
    "responder": {
      "calls": 20,
      "input_tokens": 31043,
      "cached_read_tokens": 0,
      "cache_write_tokens": 30983,
      "uncached_tokens": 60,
      "output_tokens": 1576,
      "latency_ms": 37343,
      "retries": 0,
      "fallback_calls": 0
    },
    "all": {
      "calls": 40,
      "input_tokens": 154639,
      "cached_read_tokens": 107060,
      "cache_write_tokens": 30983,
      "uncached_tokens": 16596,
      "output_tokens": 6840,
      "latency_ms": 99502,
      "retries": 0,
      "fallback_calls": 0
    },
    "turn_latency_ms": 164279
  },
  "cost": {
    "actual_usd": 0.02141415,
    "without_explicit_cache_usd": 0.0391358,
    "saving_usd": 0.01772165,
    "saving_percent": 45.28
  },
  "stopped_for_deterministic_p0": false
}
