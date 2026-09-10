"use server";

import { revalidatePath } from "next/cache";

import { TiaApiError, tiaRequest } from "@/lib/tia/api";

export type DoctorAdminState = {
  notice: string | null;
  error: string | null;
};

export const initialDoctorAdminState: DoctorAdminState = { notice: null, error: null };

type WorkingHourInterval = {
  weekday: number;
  start_time: string;
  end_time: string;
};

function clean(value: FormDataEntryValue | null) {
  const normalized = String(value || "").trim();
  return normalized || null;
}

function serviceIds(formData: FormData) {
  return [...new Set(formData.getAll("service_id").map((value) => String(value).trim()).filter(Boolean))];
}

function parseIntervals(formData: FormData): WorkingHourInterval[] {
  const raw = String(formData.get("intervals_json") || "[]");
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("مواعيد العمل غير صالحة. راجع الأيام والساعات وحاول مرة أخرى.");
  }
  if (!Array.isArray(value)) throw new Error("مواعيد العمل غير صالحة.");
  const intervals: WorkingHourInterval[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") throw new Error("مواعيد العمل غير صالحة.");
    const row = item as Record<string, unknown>;
    const weekday = Number(row.weekday);
    const startTime = String(row.start_time || "");
    const endTime = String(row.end_time || "");
    if (!Number.isInteger(weekday) || weekday < 0 || weekday > 6) throw new Error("يوم العمل غير صالح.");
    if (!/^\d{2}:\d{2}$/.test(startTime) || !/^\d{2}:\d{2}$/.test(endTime) || endTime <= startTime) {
      throw new Error("وقت نهاية كل فترة لازم يكون بعد وقت البداية.");
    }
    intervals.push({ weekday, start_time: startTime, end_time: endTime });
  }
  return intervals;
}

function stateFromError(error: unknown): DoctorAdminState {
  if (error instanceof TiaApiError) {
    return { notice: null, error: error.technicalMessage || error.message };
  }
  if (error instanceof Error) return { notice: null, error: error.message };
  return { notice: null, error: "تعذر تنفيذ التعديل. حاول مرة أخرى." };
}

function refreshDoctorViews() {
  revalidatePath("/doctors");
  revalidatePath("/appointments");
  revalidatePath("/dashboard");
  revalidatePath("/knowledge");
}

export async function createDoctorAction(
  _previousState: DoctorAdminState,
  formData: FormData,
): Promise<DoctorAdminState> {
  try {
    const firstName = clean(formData.get("first_name"));
    const lastName = clean(formData.get("last_name"));
    const branchId = clean(formData.get("branch_id"));
    const selectedServices = serviceIds(formData);
    if (!firstName || !lastName || !branchId) {
      return { notice: null, error: "الاسم والفرع بيانات مطلوبة." };
    }
    if (!selectedServices.length) {
      return { notice: null, error: "اختار خدمة واحدة على الأقل للدكتور." };
    }
    await tiaRequest("/clinic/doctor-admin", {
      method: "POST",
      body: JSON.stringify({
        first_name: firstName,
        last_name: lastName,
        email: clean(formData.get("email")),
        phone: clean(formData.get("phone")),
        specialization: clean(formData.get("specialization")),
        branch_id: branchId,
        service_ids: selectedServices,
        booking_enabled: true,
        working_hours: { intervals: parseIntervals(formData) },
      }),
    });
    refreshDoctorViews();
    return { notice: "تمت إضافة الدكتور ومواعيد عمله بنجاح.", error: null };
  } catch (error) {
    return stateFromError(error);
  }
}

export async function updateDoctorAction(
  _previousState: DoctorAdminState,
  formData: FormData,
): Promise<DoctorAdminState> {
  try {
    const doctorId = clean(formData.get("doctor_id"));
    const firstName = clean(formData.get("first_name"));
    const lastName = clean(formData.get("last_name"));
    const selectedServices = serviceIds(formData);
    if (!doctorId || !firstName || !lastName) {
      return { notice: null, error: "بيانات الدكتور غير مكتملة." };
    }
    if (!selectedServices.length) {
      return { notice: null, error: "اختار خدمة واحدة على الأقل للدكتور." };
    }
    await tiaRequest(`/clinic/doctor-admin/${doctorId}`, {
      method: "PATCH",
      body: JSON.stringify({
        first_name: firstName,
        last_name: lastName,
        email: clean(formData.get("email")),
        phone: clean(formData.get("phone")),
        specialization: clean(formData.get("specialization")),
        service_ids: selectedServices,
        booking_enabled: formData.get("booking_enabled") === "on",
      }),
    });
    refreshDoctorViews();
    return { notice: "تم تحديث بيانات الدكتور والخدمات المتاحة له.", error: null };
  } catch (error) {
    return stateFromError(error);
  }
}

export async function updateDoctorScheduleAction(
  _previousState: DoctorAdminState,
  formData: FormData,
): Promise<DoctorAdminState> {
  try {
    const doctorId = clean(formData.get("doctor_id"));
    const branchId = clean(formData.get("branch_id"));
    if (!doctorId || !branchId) return { notice: null, error: "بيانات الدكتور أو الفرع غير مكتملة." };
    await tiaRequest(`/clinic/doctors/${doctorId}/branches/${branchId}/working-hours`, {
      method: "PUT",
      body: JSON.stringify({ intervals: parseIntervals(formData) }),
    });
    refreshDoctorViews();
    return { notice: "تم تحديث مواعيد العمل لهذا الفرع.", error: null };
  } catch (error) {
    return stateFromError(error);
  }
}

export async function removeDoctorAction(
  _previousState: DoctorAdminState,
  formData: FormData,
): Promise<DoctorAdminState> {
  try {
    const doctorId = clean(formData.get("doctor_id"));
    if (!doctorId) return { notice: null, error: "تعذر تحديد الدكتور." };
    await tiaRequest(`/clinic/doctor-admin/${doctorId}`, { method: "DELETE" });
    refreshDoctorViews();
    return { notice: "تمت إزالة الدكتور من الحجز النشط مع الاحتفاظ بالسجل التاريخي.", error: null };
  } catch (error) {
    return stateFromError(error);
  }
}
