# Agent Eval Batch 2 — Integrated Closeout Revalidation

## Verdict

**BATCH 2 NOT CLOSED**

RC1–RC7 all revalidated successfully in the integrated runtime, but Scenario 22 introduced a new P1 cross-regression in canonical-fact continuity. The frozen run performed no Agent runtime fixes.

## Run identity

- Task branch: `eval/agent-batch-02-closeout`
- Starting main SHA: `c9d59cdb7863439d0faa2f352b5cb471dad7e7ba`
- CLOSEOUT_BASE_SHA: `c9d59cdb7863439d0faa2f352b5cb471dad7e7ba`
- Harness SHA: `c9d59cdb7863439d0faa2f352b5cb471dad7e7ba` (no harness change before run)
- Scenario version: `batch2-v1`
- Demo seed: `batch2-demo-fixtures-v1`
- Model: `gpt-5.6-luna`
- Fallback model: `gpt-5-mini`
- Reasoning effort: `low`
- Timestamp: `2026-09-25T08:09:06.457933+00:00`
- Official live evaluation deployment: `d25246c4-056d-4465-a6f4-36bb12dc8104`
- Production tia-api verified before run: deployment `03539d33-0b3c-406e-8064-6e34b5c46d21`, SUCCESS on the same main SHA.

Repository discrepancy note: the checked-in original Batch 2 review records frozen runtime base `adebcf54aa9f152da10dab0f250f69d27f8e6223`; this report treats the repository review as source of truth rather than the handoff text's differing SHA suffix.

## Pricing

Verified 2026-09-25 against the current OpenAI API pricing source used for the run: input $0.20/M, cached input $0.02/M, output $1.20/M, explicit cache-write multiplier 1.25× normal input. No optimization changes were made.

## Closeout totals

| Metric | Closeout |
|---|---:|
| Scenarios | 24 |
| Customer turns | 51 |
| LLM calls | 98 |
| Interpreter calls | 51 |
| Responder calls | 47 |
| Input tokens | 371,197 |
| Cached read | 218,050 |
| Cache write | 82,704 |
| Uncached input | 70,443 |
| Output tokens | 16,809 |
| Total tokens | 388,006 |
| Provider LLM latency | 301,749 ms |
| Retries | 0 |
| Fallback model calls | 0 |
| Actual cost | $0.0592964 |
| No-cache equivalent | $0.0944102 |
| Cache saving | 37.19% |

| Provider stage | Calls | Input | Cached read | Cache write | Uncached | Output | Latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| Interpreter | 51 | 292,713 | 218,050 | 4,361 | 70,302 | 13,091 | 196,250 |
| Responder | 47 | 78,484 | 0 | 78,343 | 141 | 3,718 | 105,499 |

The 98-call count is not an infrastructure loss: all 51 turns completed, metadata_missing_calls = 0, retries = 0, fallbacks = 0. Deterministic recent-action acknowledgments reduce responder calls on some completion paths.

## Comparison against original reviewed Batch 2

| Metric | Original Batch 2 | Closeout |
|---|---:|---:|
| Scenarios | 24 | 24 |
| Customer turns | 51 | 51 |
| LLM calls | 100 | 98 |
| Input tokens | 351,720 | 371,197 |
| Output tokens | 16,401 | 16,809 |
| Total tokens | 368,121 | 388,006 |
| Cached read | 217,516 | 218,050 |
| Cache write | 71,591 | 82,704 |
| Uncached input | 62,613 | 70,443 |
| Actual cost | $0.05445187 | $0.0592964 |
| No-cache equivalent | $0.09002520 | $0.0944102 |
| Cache saving | 39.51% | 37.19% |
| P0 | 0 | 0 |
| P1 | 3 | 1 |
| P2 | 6 | 0 |
| P3 | 3 | 0 |
| Fully correct | 12 | 23 |
| Acceptable/minor | 8 | 0 |
| Failed | 4 | 1 |

Prompt caching remains functional: cached reads increased slightly and the batch still saves 37.19% versus the no-cache equivalent. The lower saving percentage by itself is not treated as a cache regression because provider cache-write state and the input mix differ; there were no missing usage metadata calls.

## Manual result summary

- FULLY CORRECT: 23 scenarios (1–21 except 22, plus 23–24)
- ACCEPTABLE / MINOR: 0
- FAILED: Scenario 22
- P0: 0
- P1: 1
- P2: 0
- P3: 0
- Evaluator false positives: 0
- Infrastructure failures inside the official 24-scenario batch: 0
- Pre-run runner setup noise: five Railway redeploy/snapshot attempts failed before any scenario execution because the old eval snapshot kept its Ruff cache/start configuration. They are excluded from product severity and from the official run metrics.

## RC regression matrix

| RC | Result | Integrated live evidence |
|---|---|---|
| RC1 | **PASS** | Scenario 7 returned the 1000-Pulse Candela offer at EGP 800 and independently computed 500 overage Pulses at EGP 500. Reads were separately scoped; DB delta had no writes. |
| RC2 | **PASS** | Scenario 8 made zero financial DB reads, invented no amount, performed no write, and created exactly one human handoff. The frozen scenario input is ledger-only; mixed-info normalization remains deterministic-test coverage and was not added to the primary 24. |
| RC3 | **PASS** | Scenario 9 replacement retained `billing_context=pulse_prepaid`, Candela device, and `rescheduled_from_appointment_id`; no PaymentTransaction, PulseUsage, settlement, or balance mutation was created. |
| RC4 | **PASS** | Scenarios 11, 12, 17, 21 retained known date/service/doctor/device as appropriate; explicit corrections won; side pricing did not destroy booking state; unnecessary known-field clarification count = 0. |
| RC5 | **PASS** | Scenario 14 primary 2026-09-28 12:00 had one canonical option, and execution produced one primary outcome only; the conditional fallback was not executed. The frozen scenario does not exercise the unavailable branch; deterministic orchestrator coverage remains in backend tests. |
| RC6 | **PASS** | Scenario 16 first turn compared doctors informationally with zero write. Selecting Maha only created an awaiting-choice booking state; still zero appointment write until a time is selected. |
| RC7 | **PASS** | S5 acknowledged package-backed booking without Pulse settlement text; S10 second cancel confirmation had 0 reads/0 writes and said already cancelled; S19 repeated effective booking had 0 reads/0 writes and one total appointment, with an already-booked acknowledgment. |

## Scenario table

| ID | Name | Turns | Expected | Observed | Verified reads | Writes / DB delta | Final-response assessment | Tokens | Cost | Result | Severity | Root layer | Notes |
|---:|---|---:|---|---|---|---|---|---:|---:|---|---|---|---|
| 01 | Compound price + booking | 2 | Verified PRP price plus correct booking progression without losing either intent. | Final reply: تمام، تم حجز جلسة PRP للبشرة يوم 26 سبتمبر الساعة 10:00 صباحًا مع مها. | service_catalog, availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 18,513 | $0.00438337 | FULLY CORRECT | - | - | No material issue. |
| 02 | Two services in one turn | 1 | PRP hair price is answered while the appointment created is laser underarm on Candela. | Final reply: جلسة PRP للشعر بـ2200 جنيه. وتم حجز جلسة ليزر إزالة الشعر - إبط على جهاز Candela Gentle مع د. أحمد محمود يوم 28 سبتمبر 2026 الساعة 12:00، بسعر 650 جنيه. | service_catalog, availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 7,202 | $0.00115862 | FULLY CORRECT | - | - | No material issue. |
| 03 | Buy Pulse pack + book | 1 | Pulse entitlement created; booking remains standard; no payment, usage, or settlement is invented. | Final reply: تم حجز جلسة ليزر إزالة الشعر - إبط مع أحمد محمود يوم 28 سبتمبر الساعة 12:00 على جهاز Candela Gentle، وسعر الجلسة 650 جنيه. كمان تم تسجيل طلب باقة 1000 Pulse بسعر 800 جنيه، لكن الدفع نفسه لم يُسجَّل في العملية دي؛ للتسوية أو الدفع تواصلي مع الاستقبال. | pulse_pack_offers, availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +1; payments +0; usage +0; settlement +0; balance candela_gentle:1000; handoffs 0 | Grounded and consistent with DB effect | 7,418 | $0.00130367 | FULLY CORRECT | - | - | No material issue. |
| 04 | Explicitly ask to use Pulses | 1 | Booking continues with standard billing, no Pulse mutation, and response explains Reception settlement ownership. | Final reply: تم حجز جلسة ليزر إزالة الشعر - إبط يوم 28 سبتمبر الساعة 12:00 مع أحمد محمود باستخدام جهاز Candela Gentle. بالنسبة لاستخدام الـPulses في الدفع، التسوية بتتم مع الريسبشن. | availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 7,112 | $0.00110667 | FULLY CORRECT | - | - | No material issue. |
| 05 | Pulse balance + session package | 1 | Session package backs appointment; Pulse state remains untouched. | Final reply: تم حجز جلسة PRP للبشرة مع د. مها يوم 26 سبتمبر الساعة 10:00، واستخدمنا الباكدج الموجود عندك للحجز. | availability | 1 write turn(s); appt +1/~0; pkg +0/~1; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 6,990 | $0.00095062 | FULLY CORRECT | - | - | RC7 package-backed acknowledgment is explicit; no Pulse-settlement wording. |
| 06 | Counted Pulse overage | 1 | Overage pricing only; deterministic total from verified unit price. | Final reply: الـ1000 Pulse الإضافيين على جهاز Candela Gentle هيكونوا بـ1000 جنيه مصري، بسعر 1 جنيه لكل Pulse. | pulse_billing_settings | 0 write turn(s); appt +0/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 6,641 | $0.00080197 | FULLY CORRECT | - | - | No material issue. |
| 07 | Pulse pack offers + overage | 1 | Both verified pack offers and 500-Pulse overage total are answered independently. | Final reply: باقة Candela Gentle المتاحة هي 1000 Pulse بسعر 800 جنيه. ولو عايزة 500 Pulse زيادة من غير باقة، التكلفة هتكون 500 جنيه (1 جنيه لكل Pulse). | pulse_pack_offers, pulse_billing_settings, customer_packages | 0 write turn(s); appt +0/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 6,946 | $0.00104697 | FULLY CORRECT | - | - | RC1: 1000-Pulse offer = EGP 800; 500-Pulse overage = EGP 500; no writes. |
| 08 | Pulse financial ledger | 1 | No unsupported ledger answer; Reception or handoff guidance. | Final reply: هحوّل سؤالك للاستقبال عشان يراجعوا لكِ كام فاضل في باقة الـPulse بتاعتك ويردّوا عليكِ. | none | 0 write turn(s); appt +0/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 1 | Grounded and consistent with DB effect | 6,565 | $0.00076687 | FULLY CORRECT | - | - | RC2: no financial DB reads/amount invention/write; exactly one handoff. Frozen live scenario is ledger-only; mixed safe-info+ledger remains covered by deterministic RC2 tests, not an added live scenario. |
| 09 | Reschedule Pulse-billed appointment | 2 | Reschedule preserves pulse_prepaid state with no new Pulse/payment artifacts. | Final reply: تمام، تم تغيير ميعادك ليوم 28 سبتمبر 2026 الساعة 12:00 ظهرًا لليزر إزالة الشعر - إبط مع د. أحمد محمود في Tia Clinic. | appointments, availability | 1 write turn(s); appt +1/~1; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 14,635 | $0.00229939 | FULLY CORRECT | - | - | RC3: pulse_prepaid/device/lifecycle linkage preserved; no payment/PulseUsage/settlement mutations. |
| 10 | Cancel Pulse-billed appointment | 2 | Appointment cancels canonically; Agent performs no Pulse accounting. | Final reply: تمام، ميعادك اتلغى بالفعل. | appointments | 1 write turn(s); appt +0/~1; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 13,664 | $0.00176074 | FULLY CORRECT | - | - | RC7: second confirmation used recent verified action; 0 reads, 0 writes, reply says already cancelled. |
| 11 | Change service mid-flow | 3 | Hydrafacial replaces PRP; any eventual write uses only new service constraints. | Final reply: تمام، تم حجز جلسة هيدرافيشل مع أحمد محمود يوم 28 سبتمبر الساعة 12:00 ظهرًا، بسعر 1800 جنيه. | availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 22,713 | $0.00342161 | FULLY CORRECT | - | - | RC4: explicit service correction won while known date was retained. |
| 12 | Change doctor mid-flow | 3 | Second doctor wins; no write may use stale first doctor. | Final reply: تمام، تم حجز PRP للبشرة مع نور علي يوم 29 سبتمبر الساعة 3:00 مساءً، بسعر 2000 جنيه. | availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 20,795 | $0.00292886 | FULLY CORRECT | - | - | RC4: explicit doctor correction won while date/service survived. |
| 13 | Change laser device mid-flow | 3 | Candela wins and availability/pricing scope is refreshed. | Final reply: تمام، تم حجز جلسة ليزر إزالة الشعر للإبط على جهاز Candela Gentle مع د. أحمد محمود يوم 28 سبتمبر الساعة 12:00 ظهرًا، بسعر 650 جنيه. | availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 28,979 | $0.00475426 | FULLY CORRECT | - | - | No material issue. |
| 14 | Conditional availability fallback | 1 | Use first choice when available; inspect fallback only if first has no options. | Final reply: متاح هيدرافيشل مع أحمد محمود يوم 28 سبتمبر الساعة 12:00 ظهرًا، وسعر الجلسة 1800 جنيه. | availability | 0 write turn(s); appt +0/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 7,167 | $0.00129727 | FULLY CORRECT | - | - | RC5: primary was available; only primary outcome executed. Unavailable branch remains deterministic-test coverage because frozen Scenario 14 exercises the available branch. |
| 15 | Egyptian 12-hour ambiguity | 2 | Ambiguous 1 resolves to clinic-valid 13:00, not invented AM/PM. | Final reply: أيوه، الساعة 1 كانت متاحة يوم 26 سبتمبر مع مها، وحجزك لـ PRP للبشرة اتأكد بالفعل. | availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 18,107 | $0.00311484 | FULLY CORRECT | - | - | No material issue. |
| 16 | Compare doctors then select | 2 | First turn compares set; second short turn selects without identity ambiguity. | Final reply: تمام، مع مها متاح يوم 25 سبتمبر من 2:00 لـ3:45 ظهرًا، ومن 5:30 لـ9:00 مساءً. تحبي أي وقت؟ | availability | 0 write turn(s); appt +0/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 14,179 | $0.00206959 | FULLY CORRECT | - | - | RC6: comparison stayed informational; doctor selection started booking but did not write without time. |
| 17 | Topic switch and resume | 5 | PRP price is answered, then laser booking resumes without service leakage. | Final reply: تمام، نكمّل الحجز يوم 28 سبتمبر لجلسة الإبط بجهاز Candela Gentle بسعر 650 جنيه. اختاري الدكتور والوقت المناسب: أحمد محمود من 12:00 لـ5:45 أو من 6:15 لـ9:00، عمر خليل من 2:00 لـ4:15 أو من 5:15 لـ5:45 أو من 6:15 لـ9:00، ومريم حسن من 10:00 لـ5:00. | availability, service_catalog | 0 write turn(s); appt +0/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 48,743 | $0.00757010 | FULLY CORRECT | - | - | RC4: PRP side query did not destroy laser service/device/date task. |
| 18 | Change mind completely | 2 | Active task closes and no appointment is created. | Final reply: تمام، لغيت طلب الحجز. لو احتجتي أي حاجة تانية أنا معاكي. | none | 0 write turn(s); appt +0/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 13,300 | $0.00163014 | FULLY CORRECT | - | - | No material issue. |
| 19 | Duplicate customer text/effective booking | 2 | At most one appointment after repeated request. | Final reply: الحجز ده اتعمل بالفعل لنفس جلسة ليزر إزالة الشعر - إبط يوم 28 سبتمبر 2026 الساعة 12:00 مع أحمد محمود. | availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 14,046 | $0.00203599 | FULLY CORRECT | - | - | RC7: one appointment total; repeated effective booking had 0 reads and 0 writes and acknowledged existing booking. |
| 20 | Same-turn corrections | 1 | Final meaning is PRP hair on corrected date/time only. | Final reply: تم حجز جلسة PRP للشعر يوم 26 سبتمبر الساعة 10:00 صباحًا مع د. هالة مصطفى. السعر 2200 جنيه. | availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 7,028 | $0.00101732 | FULLY CORRECT | - | - | No material issue. |
| 21 | Long returning customer | 9 | Verified history and Pulse facts survive long history and topic switches; final explicit Candela booking wins. | Final reply: تم تأكيد حجزك يوم 28 سبتمبر 2026 الساعة 12:00 ظهرًا مع أحمد محمود، لجلسة ليزر إزالة الشعر للإبط على جهاز Candela Gentle، بسعر 650 جنيه. | customer_history, doctors, pulse_balance, service_catalog, availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 61,120 | $0.00847998 | FULLY CORRECT | - | - | RC4: no stale context leak; explicit current dimensions won; 0 unnecessary known-field clarifications. |
| 22 | DB fact vs stale chat | 3 | Agent states DB-backed last service, not stale chat, and follow-on booking remains canonical. | Turn 1 grounded PRP from DB; turns 2–3 lost that fact after stale Hydrafacial prose and ended in false PRP/Hydrafacial ambiguity. | customer_history | 0 write turn(s); appt +0/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Misleading/ungrounded continuity on last-service fact | 21,854 | $0.00319841 | **FAILED** | **P1** | Context / continuity; state management | NEW P1 cross-regression: turn 1 correctly verified last completed service as PRP skin; turn 2 introduced stale Hydrafacial ambiguity without a read; turn 3 lost the canonical fact and asked PRP vs Hydrafacial instead of retaining PRP. |
| 23 | Long stale-history control | 1 | Current underarm, Candela, doctor, date, and time win completely; no old context leakage. | Final reply: تم حجز جلسة ليزر إزالة الشعر - إبط على جهاز كانديلا مع د. أحمد محمود يوم 28 سبتمبر الساعة 12:00 ظهرًا. السعر 650 جنيه. | availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 7,231 | $0.00114167 | FULLY CORRECT | - | - | Long control: explicit current underarm/Candela/doctor/date/time won; no false duplicate acknowledgment. |
| 24 | Short control | 1 | Same final booking correctness as long-history control with minimal history overhead. | Final reply: تم حجز جلسة ليزر إزالة الشعر - إبط على جهاز Candela Gentle مع أحمد محمود يوم 28 سبتمبر الساعة 12:00. السعر 650 جنيه. | availability | 1 write turn(s); appt +1/~0; pkg +0/~0; pulsePack +0; payments +0; usage +0; settlement +0; balance 0; handoffs 0 | Grounded and consistent with DB effect | 7,058 | $0.00105747 | FULLY CORRECT | - | - | Short control reached the same DB target as Scenario 23. |

## Long-history revalidation

- History fixture size: 32 prior messages for the long-history fixtures.
- DB history loader limit: 24 messages.
- Native messages exposed to interpreter: maximum 6.
- Maximum active_task size in Scenarios 21–24: 0 estimated tokens.
- Maximum semantic context size in Scenarios 21–24: 925 estimated tokens (Scenario 21 turn 3).
- Maximum recent verified-read context in Scenarios 21–24: 63 estimated tokens.
- Old context leaked: **YES — Scenario 22 only**.
- Current explicit request won: **NO overall** because Scenario 22's “same thing I actually did last time” could not resolve to the already verified PRP fact. Explicit current dimensions did win in Scenarios 21, 23, and 24.
- Canonical DB facts beat stale chat: **NO across the whole long-history family**. Scenario 22 turn 1 did, but turns 2–3 regressed to ambiguity.
- False duplicate acknowledgment observed: **NO**.
- False already-cancelled acknowledgment observed: **NO**.

### Short vs long control

| Metric | Scenario 24 short | Scenario 23 long |
|---|---:|---:|
| Final DB result | Correct target booking | Correct same target booking |
| LLM calls | 2 | 2 |
| Input tokens | 6706 | 6833 |
| Cached read | 4361 | 4361 |
| Uncached input | 768 | 823 |
| Latency | 5926 ms | 6736 ms |
| Cost | $0.00105747 | $0.00114167 |

Quality degradation for the controlled Scenario 23 vs 24 pair: **NONE**. The long control adds 1.89% input and 13.67% measured latency but reaches the same semantic and DB result. The material long-history problem is isolated to Scenario 22's verified-fact continuity, not general history length.

## Genuine failure: Scenario 22

**Severity:** P1  
**Root layer:** Context / continuity + state management  
**Evidence:** Turn 1 performed `customer_history` verified read and correctly stated canonical last completed service = PRP skin. Turn 2 was a `continues_previous=true` customer-history continuation but executed no canonical read. Live V2 persists `v2_read_context` from only the current turn, so that outbound stored no read context. Turn 3 therefore received no recent verified-read fact and treated PRP vs stale Hydrafacial prose as unresolved. This is a regression versus the original reviewed Scenario 22, which was Fully Correct.

No runtime fix is included in this closeout branch. The separate root-cause task document compares solution options and recommends a bounded verified-read carry-forward for no-read same-topic continuations.

## Final gate decision

The closeout does **not** satisfy the requested close condition because there is one unresolved P1 and a material cross-regression in the rule `canonical DB facts > stale conversation prose`. Financial boundaries remain intact, DB effects are correct in all write scenarios, and RC1–RC7 targeted regressions themselves remain closed.

**Final verdict: BATCH 2 NOT CLOSED**
