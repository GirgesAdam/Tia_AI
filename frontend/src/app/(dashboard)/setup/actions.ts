"use server";
import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";
import type { OnboardingAIActionState, OnboardingAIResponse } from "@/lib/onboarding-ai-types";

const s=(f:FormData,k:string)=>String(f.get(k)||"").trim();
const n=(f:FormData,k:string,d=0)=>Number(s(f,k)||d);
const b=(f:FormData,k:string)=>f.get(k)==="on"||f.get(k)==="true";

function refresh(){revalidatePath("/setup");revalidatePath("/dashboard");}

export async function createBranch(formData:FormData){
  await tiaRequest("/clinic/branches",{method:"POST",body:JSON.stringify({
    name:s(formData,"name"),code:s(formData,"code"),phone:s(formData,"phone")||null,
    address_line1:s(formData,"address_line1")||null,city:s(formData,"city")||null,
    country_code:"EG",timezone:s(formData,"timezone")||"Africa/Cairo"
  })});refresh();
}
export async function createService(formData:FormData){
  await tiaRequest("/clinic/services",{method:"POST",body:JSON.stringify({
    name:s(formData,"name"),slug:s(formData,"slug"),category:s(formData,"category")||null,
    duration_minutes:n(formData,"duration_minutes",60),buffer_before_minutes:n(formData,"buffer_before_minutes"),
    buffer_after_minutes:n(formData,"buffer_after_minutes"),price_minor:Math.round(n(formData,"price_egp")*100),
    currency:"EGP",requires_medical_review:b(formData,"requires_medical_review")
  })});refresh();
}
export async function createDoctor(formData:FormData){
  const staff=await tiaRequest<{id:string}>("/clinic/staff",{method:"POST",body:JSON.stringify({
    first_name:s(formData,"first_name"),last_name:s(formData,"last_name"),phone:s(formData,"phone")||null,
    email:s(formData,"email")||null,job_title:"doctor",user_id:null
  })});
  await tiaRequest("/clinic/doctors",{method:"POST",body:JSON.stringify({
    staff_id:staff.id,specialization:s(formData,"specialization")||null,license_number:s(formData,"license_number")||null,
    bio:null,booking_enabled:true
  })});refresh();
}
export async function assignDoctorBranch(formData:FormData){
  const doctor=s(formData,"doctor_id"),branch=s(formData,"branch_id");
  await tiaRequest(`/clinic/doctors/${doctor}/branches/${branch}`,{method:"PUT",body:JSON.stringify({is_primary:b(formData,"is_primary"),is_active:true})});refresh();
}
export async function assignDoctorService(formData:FormData){
  const doctor=s(formData,"doctor_id"),service=s(formData,"service_id");
  await tiaRequest(`/clinic/doctors/${doctor}/services/${service}`,{method:"PUT",body:JSON.stringify({custom_duration_minutes:null,custom_price_minor:null,is_active:true})});refresh();
}
function intervals(formData:FormData){
  const rows=[] as Array<{weekday:number;start_time:string;end_time:string}>;
  for(let day=0;day<7;day++){
    if(!b(formData,`day_${day}`)) continue;
    const start=s(formData,`start_${day}`),end=s(formData,`end_${day}`);
    if(start&&end) rows.push({weekday:day,start_time:start,end_time:end});
  }
  return rows;
}
export async function saveBranchHours(formData:FormData){
  const id=s(formData,"branch_id");
  await tiaRequest(`/clinic/branches/${id}/working-hours`,{method:"PUT",body:JSON.stringify({intervals:intervals(formData)})});refresh();
}
export async function saveDoctorHours(formData:FormData){
  const doctor=s(formData,"doctor_id"),branch=s(formData,"branch_id");
  await tiaRequest(`/clinic/doctors/${doctor}/branches/${branch}/working-hours`,{method:"PUT",body:JSON.stringify({intervals:intervals(formData)})});refresh();
}
export async function saveBookingSettings(formData:FormData){
  await tiaRequest("/clinic/booking-settings",{method:"PUT",body:JSON.stringify({
    slot_interval_minutes:n(formData,"slot_interval_minutes",15),minimum_notice_minutes:n(formData,"minimum_notice_minutes",60),
    booking_horizon_days:n(formData,"booking_horizon_days",90),cancellation_notice_minutes:n(formData,"cancellation_notice_minutes",720),
    allow_same_day_booking:b(formData,"allow_same_day_booking"),require_confirmation:b(formData,"require_confirmation"),default_currency:"EGP"
  })});refresh();
}


export async function onboardingAiAction(
  previousState: OnboardingAIActionState,
  formData: FormData,
): Promise<OnboardingAIActionState> {
  const mode = s(formData, "mode") || "chat";
  const sessionId = s(formData, "session_id") || previousState.response?.session_id || "";
  const version = Number(
    s(formData, "version") || previousState.response?.version || 0,
  );

  try {
    let response: OnboardingAIResponse;
    if (mode === "confirm") {
      if (!sessionId || !version) throw new Error("مفيش خطة صالحة للتأكيد.");
      response = await tiaRequest<OnboardingAIResponse>(
        `/onboarding/ai/sessions/${sessionId}/confirm`,
        {
          method: "POST",
          body: JSON.stringify({ expected_version: version }),
        },
      );
    } else if (mode === "cancel") {
      if (!sessionId || !version) throw new Error("مفيش جلسة إعداد حالية.");
      response = await tiaRequest<OnboardingAIResponse>(
        `/onboarding/ai/sessions/${sessionId}/cancel`,
        {
          method: "POST",
          body: JSON.stringify({ expected_version: version }),
        },
      );
    } else {
      const message = s(formData, "message");
      if (!message) throw new Error("اكتب تفاصيل الإعداد اللي عايز Tia تنفذها.");
      response = await tiaRequest<OnboardingAIResponse>("/onboarding/ai/chat", {
        method: "POST",
        body: JSON.stringify({
          message,
          session_id: sessionId || null,
          expected_version: version || null,
        }),
      });
    }

    if (response.readiness_refresh_required) refresh();
    return { response, error: null };
  } catch (error) {
    return {
      response: previousState.response,
      error: error instanceof Error ? error.message : "حصل خطأ أثناء إعداد العيادة.",
    };
  }
}
