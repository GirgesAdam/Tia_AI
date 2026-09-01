export type KnowledgeHour = { weekday: number; start_time: string; end_time: string };
export type KnowledgeBranch = {
  id: string; name: string; code: string; city: string | null; address_line1: string | null;
  phone: string | null; timezone: string | null; is_active: boolean; working_hours: KnowledgeHour[];
};
export type KnowledgeService = {
  id: string; name: string; slug: string; category: string | null; description: string | null;
  duration_minutes: number; price_minor: number; currency: string; requires_medical_review: boolean; is_active: boolean;
};
export type KnowledgeNamedLink = { id: string; name: string; is_primary: boolean };
export type KnowledgeDoctorSchedule = { branch_id: string; branch_name: string; working_hours: KnowledgeHour[] };
export type KnowledgeDoctor = {
  id: string; staff_id: string; name: string; first_name: string; last_name: string; specialization: string | null;
  phone: string | null; email: string | null; booking_enabled: boolean; is_active: boolean;
  branches: KnowledgeNamedLink[]; services: KnowledgeNamedLink[]; schedules: KnowledgeDoctorSchedule[];
};
export type KnowledgePatient = { id: string; name: string; phone: string | null; status: string; source: string };
export type KnowledgeAppointment = {
  id: string; patient_name: string; patient_phone: string | null; service_name: string; branch_name: string; doctor_name: string;
  start_at: string; end_at: string; status: string; payment_status: string; amount_paid_minor: number | null;
  payment_method: string; price_minor: number; currency: string;
};
export type BookingSettings = {
  slot_interval_minutes: number; minimum_notice_minutes: number; booking_horizon_days: number;
  cancellation_notice_minutes: number; allow_same_day_booking: boolean; require_confirmation: boolean; default_currency: string;
};
export type AgentKnowledgeSnapshot = {
  workspace_id: string; workspace_name: string; workspace_timezone: string;
  branches: KnowledgeBranch[]; services: KnowledgeService[]; doctors: KnowledgeDoctor[];
  booking_settings: BookingSettings | null; patients: KnowledgePatient[]; appointments: KnowledgeAppointment[];
  patient_count: number; appointment_count: number;
};

export type KnowledgeEditAction = Record<string, unknown>;
export type KnowledgeEditProposal = {
  base_fingerprint: string; assistant_message: string; preview_lines: string[];
  actions: KnowledgeEditAction[]; requires_confirmation: boolean; clarification_question: string | null;
};
export type KnowledgeAssistantState = {
  proposal: KnowledgeEditProposal | null;
  notice: string | null;
  error: string | null;
};
