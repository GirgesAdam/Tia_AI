from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"anchor not found in {path}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Register the calendar route.
replace_once(
    "backend/app/api/router.py",
    "from app.api.routes.dashboard import router as dashboard_router\n",
    "from app.api.routes.dashboard import router as dashboard_router\nfrom app.api.routes.doctor_calendar import router as doctor_calendar_router\n",
)
replace_once(
    "backend/app/api/router.py",
    "api_router.include_router(booking_router, prefix=\"/booking\", tags=[\"booking\"])\n",
    "api_router.include_router(booking_router, prefix=\"/booking\", tags=[\"booking\"])\napi_router.include_router(doctor_calendar_router, prefix=\"/booking\", tags=[\"booking\"])\n",
)

# Staff service edits can explicitly move the appointment to another doctor when needed.
replace_once(
    "backend/app/services/staff_appointment_edits.py",
    "    service_id: UUID,\n    laser_device_key: str | None,\n) -> SlotCandidate:",
    "    service_id: UUID,\n    doctor_id: UUID,\n    laser_device_key: str | None,\n) -> SlotCandidate:",
)
replace_once(
    "backend/app/services/staff_appointment_edits.py",
    "            doctor_id=appointment.doctor_id,\n",
    "            doctor_id=doctor_id,\n",
)
replace_once(
    "backend/app/services/staff_appointment_edits.py",
    "        \"The current appointment time is not available for the selected service/device with this doctor.\"\n",
    "        \"The current appointment time is not available for the selected service/device with the selected doctor.\"\n",
)
replace_once(
    "backend/app/services/staff_appointment_edits.py",
    "    service_id: UUID,\n    laser_device_key: str | None,\n    changed_by_user_id: UUID | None,",
    "    service_id: UUID,\n    doctor_id: UUID | None = None,\n    laser_device_key: str | None,\n    changed_by_user_id: UUID | None,",
)
replace_once(
    "backend/app/services/staff_appointment_edits.py",
    "    normalized_device = (laser_device_key or \"\").strip() or None\n    service_changed = service_id != appointment.service_id\n    device_changed = normalized_device != (appointment.laser_device_key or None)\n    if not service_changed and not device_changed:\n        return appointment\n\n    slot = _validated_slot_for_existing_appointment(\n        db,\n        workspace=workspace,\n        appointment=appointment,\n        service_id=service_id,\n        laser_device_key=normalized_device,\n    )\n\n    old_service_id = appointment.service_id\n",
    "    normalized_device = (laser_device_key or \"\").strip() or None\n    selected_doctor_id = doctor_id or appointment.doctor_id\n    service_changed = service_id != appointment.service_id\n    doctor_changed = selected_doctor_id != appointment.doctor_id\n    device_changed = normalized_device != (appointment.laser_device_key or None)\n    if not service_changed and not doctor_changed and not device_changed:\n        return appointment\n\n    slot = _validated_slot_for_existing_appointment(\n        db,\n        workspace=workspace,\n        appointment=appointment,\n        service_id=service_id,\n        doctor_id=selected_doctor_id,\n        laser_device_key=normalized_device,\n    )\n\n    old_service_id = appointment.service_id\n    old_doctor_id = appointment.doctor_id\n",
)
replace_once(
    "backend/app/services/staff_appointment_edits.py",
    "    appointment.service_id = slot.service_id\n",
    "    appointment.service_id = slot.service_id\n    appointment.doctor_id = slot.doctor_id\n",
)
replace_once(
    "backend/app/services/staff_appointment_edits.py",
    "            \"old_service_id\": old_service_id,\n            \"new_service_id\": appointment.service_id,\n",
    "            \"old_service_id\": old_service_id,\n            \"new_service_id\": appointment.service_id,\n            \"old_doctor_id\": old_doctor_id,\n            \"new_doctor_id\": appointment.doctor_id,\n",
)

# Staff API accepts an explicit compatible doctor without silently choosing one.
replace_once(
    "backend/app/api/routes/appointment_edits.py",
    "class AppointmentServiceUpdate(BaseModel):\n    service_id: UUID\n    laser_device_key:",
    "class AppointmentServiceUpdate(BaseModel):\n    service_id: UUID\n    doctor_id: UUID | None = None\n    laser_device_key:",
)
replace_once(
    "backend/app/api/routes/appointment_edits.py",
    "            service_id=payload.service_id,\n            laser_device_key=payload.laser_device_key,\n",
    "            service_id=payload.service_id,\n            doctor_id=payload.doctor_id,\n            laser_device_key=payload.laser_device_key,\n",
)

# Dashboard action returns an inline error instead of throwing a Server Action exception.
replace_once(
    "frontend/src/app/(dashboard)/appointments/[appointmentId]/actions.ts",
    'import { tiaRequest } from "@/lib/tia/api";\n',
    'import { TiaApiError, tiaRequest } from "@/lib/tia/api";\n',
)
replace_once(
    "frontend/src/app/(dashboard)/appointments/[appointmentId]/actions.ts",
    '  revalidatePath("/appointments");\n',
    '  revalidatePath("/appointments");\n  revalidatePath("/doctors");\n',
)
old_action = '''export async function changeAppointmentService(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const serviceId = String(formData.get("service_id") || "");
  const laserDeviceKey = String(formData.get("laser_device_key") || "").trim();
  if (!appointmentId || !serviceId) return;
  await tiaRequest(`/booking/appointments/${appointmentId}/service`, {
    method: "POST",
    body: JSON.stringify({
      service_id: serviceId,
      laser_device_key: laserDeviceKey || null,
    }),
  });
  refreshAppointmentViews(appointmentId, patientId || undefined);
}
'''
new_action = '''export type AppointmentServiceChangeState = { ok: boolean; error: string | null };

function serviceChangeError(error: unknown) {
  if (!(error instanceof TiaApiError)) return "تعذر تعديل الخدمة. حاول مرة أخرى.";
  const detail = error.technicalMessage || "";
  if (detail.includes("not available for the selected service/device with the selected doctor")) {
    return "الخدمة أو الجهاز الجديد مش متاحين في نفس الميعاد مع الدكتور المختار. اختار دكتور تاني أو غيّر الموعد.";
  }
  if (detail.includes("not assigned") || detail.includes("does not provide")) {
    return "الدكتور المختار غير متاح لتنفيذ الخدمة دي. اختار دكتور تاني للخدمة.";
  }
  if (detail.includes("device") && detail.includes("price")) {
    return "سعر جهاز الليزر المختار غير مفعّل للخدمة دي.";
  }
  return error.message;
}

export async function changeAppointmentService(
  _previous: AppointmentServiceChangeState,
  formData: FormData,
): Promise<AppointmentServiceChangeState> {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const serviceId = String(formData.get("service_id") || "");
  const doctorId = String(formData.get("doctor_id") || "").trim();
  const laserDeviceKey = String(formData.get("laser_device_key") || "").trim();
  if (!appointmentId || !serviceId || !doctorId) {
    return { ok: false, error: "اختار الخدمة والدكتور قبل الحفظ." };
  }
  try {
    await tiaRequest(`/booking/appointments/${appointmentId}/service`, {
      method: "POST",
      body: JSON.stringify({
        service_id: serviceId,
        doctor_id: doctorId,
        laser_device_key: laserDeviceKey || null,
      }),
    });
    refreshAppointmentViews(appointmentId, patientId || undefined);
    return { ok: true, error: null };
  } catch (error) {
    return { ok: false, error: serviceChangeError(error) };
  }
}
'''
replace_once("frontend/src/app/(dashboard)/appointments/[appointmentId]/actions.ts", old_action, new_action)

# Appointment page provides the editor with doctor choices.
replace_once(
    "frontend/src/app/(dashboard)/appointments/[appointmentId]/page.tsx",
    'import type { AppointmentOperationsDetail, AppointmentPaymentSummary } from "@/lib/types";\n',
    'import type { AppointmentOperationsDetail, AppointmentPaymentSummary, Doctor, Staff } from "@/lib/types";\n',
)
replace_once(
    "frontend/src/app/(dashboard)/appointments/[appointmentId]/page.tsx",
    "  const [detail, payments, products, productLines, services, devicePrices] = await Promise.all([\n",
    "  const [detail, payments, products, productLines, services, devicePrices, doctors, staff] = await Promise.all([\n",
)
replace_once(
    "frontend/src/app/(dashboard)/appointments/[appointmentId]/page.tsx",
    '    tiaRequest<AppointmentDevicePrice[]>("/inventory/laser-prices").catch(() => []),\n  ]);',
    '    tiaRequest<AppointmentDevicePrice[]>("/inventory/laser-prices").catch(() => []),\n    tiaRequest<Doctor[]>("/clinic/doctors").catch(() => []),\n    tiaRequest<Staff[]>("/clinic/staff").catch(() => []),\n  ]);',
)
replace_once(
    "frontend/src/app/(dashboard)/appointments/[appointmentId]/page.tsx",
    "  const overpaidMinor = Math.max(payments.net_paid_minor - payments.price_minor, 0);\n",
    "  const overpaidMinor = Math.max(payments.net_paid_minor - payments.price_minor, 0);\n  const staffMap = new Map(staff.map((item) => [item.id, `${item.first_name} ${item.last_name}`.trim()]));\n  const doctorOptions = doctors\n    .filter((item) => item.is_active)\n    .map((item) => ({ id: item.id, name: staffMap.get(item.staff_id) || \"دكتور\" }));\n",
)
replace_once(
    "frontend/src/app/(dashboard)/appointments/[appointmentId]/page.tsx",
    "                  currentServiceId={appointment.service_id}\n                  currentDeviceKey={laserAppointment.laser_device_key || null}\n",
    "                  currentServiceId={appointment.service_id}\n                  currentDoctorId={appointment.doctor_id}\n                  currentDeviceKey={laserAppointment.laser_device_key || null}\n",
)
replace_once(
    "frontend/src/app/(dashboard)/appointments/[appointmentId]/page.tsx",
    "                  services={services}\n                  devicePrices={devicePrices}\n",
    "                  services={services}\n                  doctors={doctorOptions}\n                  devicePrices={devicePrices}\n",
)

# Navigation exposes the doctor schedule as a daily-work page.
replace_once(
    "frontend/src/components/dashboard-navigation.tsx",
    "  Settings2,\n  Sparkles,\n",
    "  Settings2,\n  Sparkles,\n  Stethoscope,\n",
)
replace_once(
    "frontend/src/components/dashboard-navigation.tsx",
    '  { href: "/appointments", label: "المواعيد", icon: CalendarDays },\n',
    '  { href: "/appointments", label: "المواعيد", icon: CalendarDays },\n  { href: "/doctors", label: "الدكاترة", icon: Stethoscope },\n',
)

# The semantic interpreter always has the current patient's upcoming appointments available for
# existing-appointment edits, and includes device identity in those grounded records.
replace_once(
    "backend/app/services/agent_chat.py",
    '                "end_local": appointment.end_at.astimezone(clinic_tz).isoformat(),\n',
    '                "end_local": appointment.end_at.astimezone(clinic_tz).isoformat(),\n                "laser_device_key": appointment.laser_device_key,\n                "laser_device_name": appointment.laser_device_name,\n',
)
replace_once(
    "backend/app/services/agent_chat.py",
    '''    clinic_catalog = build_clinic_catalog(db, workspace)
    if flow is not None and flow.is_active and flow.flow_type == "appointment_reschedule":
        clinic_catalog = _with_current_patient_appointments(
            db=db,
            workspace=workspace,
            patient=patient,
            clinic_catalog=clinic_catalog,
        )
''',
    '''    clinic_catalog = build_clinic_catalog(db, workspace)
    # Existing-appointment edits can begin from a fresh customer turn. Supply only this
    # patient's upcoming appointments (max 10) so the semantic layer can ground the exact
    # appointment before the reschedule/write path; other customers are never exposed.
    clinic_catalog = _with_current_patient_appointments(
        db=db,
        workspace=workspace,
        patient=patient,
        clinic_catalog=clinic_catalog,
    )
''',
)

# A service/device correction to an existing appointment is a reschedule mutation, not a new booking.
replace_once(
    "backend/app/agents/turn_interpreter.py",
    '        "APPOINTMENT CONFIRMATION: use appointment_confirmation only when the customer wants a pending "\n',
    '        "EXISTING APPOINTMENT EDITS: when the customer asks to change the service or laser device of an "\n'
    '        "existing appointment, treat it as appointment_reschedule even when the requested date/time stays "\n'
    '        "the same. Resolve appointment_id from the supplied current-patient appointments, use "\n'
    '        "flow_signal=start_reschedule for a fresh edit flow, and never use appointment_creation merely "\n'
    '        "because the replacement service needs availability validation. Preserve the existing start time "\n'
    '        "when conversational context clearly refers to keeping that appointment time. If the old doctor "\n'
    '        "was not explicitly reaffirmed and is incompatible with the replacement service, do not preserve "\n'
    '        "that doctor as a requirement; let verified availability surface compatible doctors. Python remains "\n'
    '        "authoritative for financial handoff rules and exact-slot validation.\\n\\n"\n'
    '        "APPOINTMENT CONFIRMATION: use appointment_confirmation only when the customer wants a pending "\n',
)

# Extend the existing service-edit regression with explicit doctor changes.
test_path = ROOT / "backend/tests/test_staff_appointment_service_edit.py"
test_text = test_path.read_text(encoding="utf-8")
append_test = '''\n\ndef test_staff_service_change_can_use_explicit_compatible_doctor(monkeypatch) -> None:\n    old_service_id = uuid4()\n    new_service_id = uuid4()\n    new_doctor_id = uuid4()\n    appointment = _appointment(service_id=old_service_id, package_backed=False)\n    workspace = SimpleNamespace(id=appointment.workspace_id)\n    db = _Db()\n    new_slot = SlotCandidate(\n        branch_id=appointment.branch_id,\n        doctor_id=new_doctor_id,\n        service_id=new_service_id,\n        start_at=appointment.start_at,\n        end_at=appointment.start_at + timedelta(minutes=60),\n        busy_start_at=appointment.start_at,\n        busy_end_at=appointment.start_at + timedelta(minutes=60),\n        duration_minutes=60,\n        price_minor=100_000,\n        currency=\"EGP\",\n        laser_device_key=\"candela_gentle\",\n        laser_device_name=\"Candela Gentle\",\n    )\n    validated: list[UUID] = []\n\n    monkeypatch.setattr(edits, \"_locked_appointment\", lambda *args, **kwargs: appointment)\n    monkeypatch.setattr(\n        edits,\n        \"_validated_slot_for_existing_appointment\",\n        lambda *args, **kwargs: (validated.append(kwargs[\"doctor_id\"]) or new_slot),\n    )\n    monkeypatch.setattr(edits, \"refresh_appointment_payment_snapshots\", lambda *args, **kwargs: None)\n    monkeypatch.setattr(edits, \"record_activity_event\", lambda *args, **kwargs: None)\n\n    edits.change_appointment_service(\n        db,\n        workspace=workspace,\n        appointment_id=appointment.id,\n        service_id=new_service_id,\n        doctor_id=new_doctor_id,\n        laser_device_key=\"candela_gentle\",\n        changed_by_user_id=uuid4(),\n    )\n\n    assert validated == [new_doctor_id]\n    assert appointment.doctor_id == new_doctor_id\n    assert appointment.service_id == new_service_id\n'''
if "test_staff_service_change_can_use_explicit_compatible_doctor" not in test_text:
    test_path.write_text(test_text + append_test, encoding="utf-8")

# Static contract regressions for the fresh service-edit semantic path and doctor calendar.
contract_path = ROOT / "backend/tests/test_service_edit_doctor_calendar_contract.py"
contract_path.write_text(
    '''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[2]\n\n\ndef test_fresh_existing_appointment_service_edit_uses_reschedule_semantics() -> None:\n    interpreter = (ROOT / \"backend/app/agents/turn_interpreter.py\").read_text(encoding=\"utf-8\")\n    agent_chat = (ROOT / \"backend/app/services/agent_chat.py\").read_text(encoding=\"utf-8\")\n    assert \"EXISTING APPOINTMENT EDITS\" in interpreter\n    assert \"treat it as appointment_reschedule even when the requested date/time stays\" in interpreter\n    assert \"clinic_catalog = _with_current_patient_appointments(\" in agent_chat\n    assert '\"laser_device_key\": appointment.laser_device_key' in agent_chat\n\n\ndef test_doctor_calendar_is_bounded_and_workspace_scoped() -> None:\n    route = (ROOT / \"backend/app/api/routes/doctor_calendar.py\").read_text(encoding=\"utf-8\")\n    assert \"Doctor calendar ranges cannot exceed 42 days\" in route\n    assert \"Appointment.workspace_id == access.workspace.id\" in route\n    assert \"Appointment.status.notin_\" in route\n\n\ndef test_service_editor_handles_conflicts_inline() -> None:\n    actions = (ROOT / \"frontend/src/app/(dashboard)/appointments/[appointmentId]/actions.ts\").read_text(encoding=\"utf-8\")\n    editor = (ROOT / \"frontend/src/app/(dashboard)/appointments/[appointmentId]/service-editor.tsx\").read_text(encoding=\"utf-8\")\n    assert \"AppointmentServiceChangeState\" in actions\n    assert \"catch (error)\" in actions\n    assert \"useActionState\" in editor\n    assert \"state.error\" in editor\n''',
    encoding="utf-8",
)

# Remove temporary patch machinery from the resulting commit.
for relative in (
    "backend/scripts/apply_service_doctors_calendar_patch.py",
    ".github/workflows/apply-service-doctors-calendar-patch.yml",
):
    target = ROOT / relative
    if target.exists():
        target.unlink()
