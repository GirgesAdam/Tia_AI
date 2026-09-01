"use server";

import { revalidatePath } from "next/cache";

import { tiaRequest } from "@/lib/tia/api";
import type { CRMCohort, CohortFollowUpResult, AnalyticsAudienceActionResult, AnalyticsSavedView } from "@/lib/types";

export interface AnalyticsCohortState {
  cohort: CRMCohort | null;
  error: string | null;
}

export async function createAnalyticsCohortAction(
  previousState: AnalyticsCohortState,
  formData: FormData,
): Promise<AnalyticsCohortState> {
  const name = String(formData.get("name") || "").trim();
  const question = String(formData.get("question") || "").trim();
  const requestId = String(formData.get("request_id") || "").trim();
  const planRaw = String(formData.get("plan") || "").trim();
  if (!name || !question || !requestId || !planRaw) {
    return { cohort: previousState.cohort, error: "بيانات المجموعة غير مكتملة." };
  }
  try {
    const plan = JSON.parse(planRaw);
    const cohort = await tiaRequest<CRMCohort>("/crm/cohorts/from-analytics", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId, name, question, plan }),
    });
    return { cohort, error: null };
  } catch (error) {
    return {
      cohort: previousState.cohort,
      error: error instanceof Error ? error.message : "تعذر حفظ مجموعة العملاء.",
    };
  }
}

export interface CohortFollowUpState {
  result: CohortFollowUpResult | null;
  error: string | null;
}

export async function createCohortFollowUpAction(
  previousState: CohortFollowUpState,
  formData: FormData,
): Promise<CohortFollowUpState> {
  const cohortId = String(formData.get("cohort_id") || "").trim();
  const requestId = String(formData.get("request_id") || "").trim();
  const title = String(formData.get("title") || "").trim();
  const description = String(formData.get("description") || "").trim() || null;
  const dueAt = String(formData.get("due_at") || "").trim();
  const priority = String(formData.get("priority") || "normal").trim();
  if (!cohortId || !requestId || !title || !dueAt) {
    return { result: previousState.result, error: "حدد عنوان وميعاد المتابعة." };
  }
  try {
    const result = await tiaRequest<CohortFollowUpResult>(`/crm/cohorts/${cohortId}/follow-up-tasks`, {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId,
        assigned_user_id: null,
        priority,
        title,
        description,
        due_at: dueAt,
      }),
    });
    return { result, error: null };
  } catch (error) {
    return {
      result: previousState.result,
      error: error instanceof Error ? error.message : "حصل خطأ أثناء إنشاء مهام المتابعة.",
    };
  }
}

export interface CohortCampaignState {
  campaign: import("@/lib/types").CRMCampaign | null;
  result: import("@/lib/types").CohortCampaignConfirmResult | null;
  error: string | null;
}

export async function prepareCohortCampaignAction(
  previousState: CohortCampaignState,
  formData: FormData,
): Promise<CohortCampaignState> {
  const cohortId = String(formData.get("cohort_id") || "").trim();
  const requestId = String(formData.get("request_id") || "").trim();
  const name = String(formData.get("name") || "").trim();
  const connectionId = String(formData.get("channel_connection_id") || "").trim();
  const templateName = String(formData.get("template_name") || "").trim();
  const templateLanguage = String(formData.get("template_language") || "ar").trim() || "ar";
  const rateLimit = Number(formData.get("rate_limit_per_minute") || 10);
  const bodyParameterKeys = formData.getAll("body_parameter_keys").map(String);
  if (!cohortId || !requestId || !name || !connectionId || !templateName) {
    return { ...previousState, error: "اختر حساب واتساب واكتب اسم قالب رسالة معتمد قبل المراجعة." };
  }
  try {
    const campaign = await tiaRequest<import("@/lib/types").CRMCampaign>(`/crm/cohorts/${cohortId}/campaigns`, {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId,
        name,
        channel_connection_id: connectionId,
        template_name: templateName,
        template_language: templateLanguage,
        body_parameter_keys: bodyParameterKeys,
        rate_limit_per_minute: rateLimit,
      }),
    });
    return { campaign, result: null, error: null };
  } catch (error) {
    return { ...previousState, error: error instanceof Error ? error.message : "تعذر تجهيز مراجعة الحملة." };
  }
}

export async function confirmCohortCampaignAction(
  previousState: CohortCampaignState,
  formData: FormData,
): Promise<CohortCampaignState> {
  const campaignId = String(formData.get("campaign_id") || "").trim();
  const confirmationId = String(formData.get("confirmation_id") || "").trim();
  if (!campaignId || !confirmationId) return { ...previousState, error: "تعذر تأكيد الإرسال. حدّث الصفحة وحاول مرة أخرى." };
  try {
    const result = await tiaRequest<import("@/lib/types").CohortCampaignConfirmResult>(`/crm/campaigns/${campaignId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ confirmation_id: confirmationId }),
    });
    return { ...previousState, result, error: null };
  } catch (error) {
    return { ...previousState, error: error instanceof Error ? error.message : "حصل خطأ أثناء تأكيد الإرسال." };
  }
}


export interface AnalyticsAudienceActionState {
  result: AnalyticsAudienceActionResult | null;
  error: string | null;
}

export async function confirmAnalyticsAudienceAction(
  previousState: AnalyticsAudienceActionState,
  formData: FormData,
): Promise<AnalyticsAudienceActionState> {
  const requestId = String(formData.get("request_id") || "").trim();
  const audienceRequestId = String(formData.get("audience_request_id") || "").trim();
  const name = String(formData.get("name") || "").trim();
  const question = String(formData.get("question") || "").trim();
  const planRaw = String(formData.get("plan") || "").trim();
  const actionKind = String(formData.get("action_kind") || "save_audience").trim();
  const title = String(formData.get("title") || "").trim() || null;
  const description = String(formData.get("description") || "").trim() || null;
  const dueAt = String(formData.get("due_at") || "").trim() || null;
  const priority = String(formData.get("priority") || "normal").trim();
  if (!requestId || !audienceRequestId || !name || !question || !planRaw) {
    return { result: previousState.result, error: "بيانات مجموعة العملاء ناقصة." };
  }
  try {
    const plan = JSON.parse(planRaw);
    const result = await tiaRequest<AnalyticsAudienceActionResult>("/crm/audiences/actions/confirm", {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId,
        audience_request_id: audienceRequestId,
        name,
        question,
        plan,
        action_kind: actionKind,
        assigned_user_id: null,
        priority,
        title,
        description,
        due_at: actionKind === "follow_up_tasks" ? dueAt : null,
      }),
    });
    return { result, error: null };
  } catch (error) {
    return {
      result: previousState.result,
      error: error instanceof Error ? error.message : "تعذر تنفيذ الإجراء المطلوب.",
    };
  }
}

export interface AnalyticsCatalogState {
  result: import("@/lib/types").AnalyticsCatalogRun | null;
  error: string | null;
}

function optionalString(formData: FormData, key: string) {
  const value = String(formData.get(key) || "").trim();
  return value || null;
}

function optionalInt(formData: FormData, key: string) {
  const raw = String(formData.get(key) || "").trim();
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? Math.trunc(value) : null;
}

function optionalBoolean(formData: FormData, key: string) {
  const raw = String(formData.get(key) || "").trim();
  if (raw === "true") return true;
  if (raw === "false") return false;
  return null;
}

export async function runAnalyticsCatalogAction(
  previousState: AnalyticsCatalogState,
  formData: FormData,
): Promise<AnalyticsCatalogState> {
  const analysisKey = String(formData.get("analysis_key") || "").trim();
  if (!analysisKey) return { result: previousState.result, error: "اختر تقريرًا أولًا." };

  const period = String(formData.get("period") || "").trim();
  const allHistory = period === "all";
  const lookbackDays = allHistory || !period ? null : Number(period);
  const serviceId = optionalString(formData, "service_id");
  const branchId = optionalString(formData, "branch_id");
  const doctorId = optionalString(formData, "doctor_id");

  try {
    const result = await tiaRequest<import("@/lib/types").AnalyticsCatalogRun>("/analytics/catalog/run", {
      method: "POST",
      body: JSON.stringify({
        analysis_key: analysisKey,
        lookback_days: typeof lookbackDays === "number" && Number.isFinite(lookbackDays) ? lookbackDays : null,
        all_history: allHistory,
        start_date: null,
        end_date: null,
        service_ids: serviceId ? [serviceId] : [],
        branch_ids: branchId ? [branchId] : [],
        doctor_ids: doctorId ? [doctorId] : [],
        comparison: formData.get("comparison") === "on",
        granularity: optionalString(formData, "granularity"),
        limit: optionalInt(formData, "limit"),
        inactivity_days: optionalInt(formData, "inactivity_days"),
        min_visits: optionalInt(formData, "min_visits"),
        max_visits: optionalInt(formData, "max_visits"),
        has_future_appointment: optionalBoolean(formData, "has_future_appointment"),
        marketing_consent: optionalBoolean(formData, "marketing_consent"),
      }),
    });
    return { result, error: null };
  } catch (error) {
    return {
      result: previousState.result,
      error: error instanceof Error ? error.message : "تعذر تشغيل التقرير حاليًا.",
    };
  }
}


export interface AnalyticsSavedViewState {
  view: AnalyticsSavedView | null;
  error: string | null;
}

export async function saveAnalyticsViewAction(
  previousState: AnalyticsSavedViewState,
  formData: FormData,
): Promise<AnalyticsSavedViewState> {
  const name = String(formData.get("name") || "").trim();
  const requestRaw = String(formData.get("request") || "").trim();
  const chart = String(formData.get("chart") || "").trim() || null;
  const displayMode = String(formData.get("display_mode") || "visual").trim();
  if (!name || !requestRaw) return { view: previousState.view, error: "اكتب اسم العرض الأول." };
  try {
    const request = JSON.parse(requestRaw);
    const view = await tiaRequest<AnalyticsSavedView>("/analytics/views", {
      method: "POST",
      body: JSON.stringify({ name, request, chart, display_mode: displayMode }),
    });
    revalidatePath("/analytics");
    return { view, error: null };
  } catch (error) {
    return {
      view: previousState.view,
      error: error instanceof Error ? error.message : "حصل خطأ أثناء حفظ العرض.",
    };
  }
}

export async function deleteAnalyticsViewAction(formData: FormData): Promise<void> {
  const viewId = String(formData.get("view_id") || "").trim();
  if (!viewId) return;
  await tiaRequest<void>(`/analytics/views/${encodeURIComponent(viewId)}`, { method: "DELETE" });
  revalidatePath("/analytics");
}
