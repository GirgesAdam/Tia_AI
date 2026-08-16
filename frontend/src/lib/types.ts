export type WorkspaceRole = "admin" | "member";

export interface CurrentUser {
  id: string;
  auth_user_id: string;
  email: string;
  full_name: string | null;
}
export interface WorkspaceAccess {
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
  role: WorkspaceRole;
}
export interface MeResponse { user: CurrentUser; workspaces: WorkspaceAccess[]; }

export interface DashboardSummary {
  active_patients: number;
  appointments_today: number;
  upcoming_appointments: number;
  open_handoffs: number;
  active_channels: number;
  failed_automation_jobs: number;
  recent_appointments: DashboardAppointment[];
}
export interface DashboardAppointment {
  id: string; patient_id: string; patient_name: string; service_name: string;
  branch_name: string; doctor_name: string; status: string; start_at: string;
  end_at: string; price_minor: number; currency: string;
}

export interface HandoffQueueItem {
  id: string; workspace_id: string; conversation_id: string; patient_id: string;
  status: "pending" | "claimed" | "resolved";
  category: string; priority: "low" | "normal" | "high" | "urgent";
  source: string; reason: string; assigned_user_id: string | null;
  created_by_user_id: string | null; claimed_at: string | null; resolved_at: string | null;
  resolved_by_user_id: string | null; resolution_note: string | null;
  created_at: string; updated_at: string; patient_name: string; patient_phone: string | null;
  channel: string; conversation_last_message_at: string | null;
  assigned_user_name: string | null; assigned_user_email: string | null;
}
export interface InboxMessage {
  id: string; conversation_id: string; channel_connection_id: string | null;
  sender_type: string; direction: string; message_type: string; content: string | null;
  delivery_status: string; sent_by_user_id: string | null; metadata_json: Record<string, unknown>;
  created_at: string;
}
export interface HandoffRead {
  id: string; workspace_id: string; conversation_id: string; patient_id: string; status: string;
  category: string; priority: string; source: string; reason: string; assigned_user_id: string | null;
  claimed_at: string | null; resolved_at: string | null; resolution_note: string | null;
  created_at: string; updated_at: string;
}
export interface InboxConversation {
  id: string; workspace_id: string; patient_id: string; channel: string; channel_connection_id: string | null;
  status: string; assigned_user_id: string | null; subject: string | null; started_at: string;
  last_message_at: string | null; closed_at: string | null;
  patient: { id: string; first_name: string; last_name: string | null; phone: string | null; email: string | null };
  active_handoff: HandoffRead | null; handoff_history: HandoffRead[]; messages: InboxMessage[];
  handoff_events: Array<{id:string; event_type:string; actor_type:string; actor_user_id:string|null; metadata_json:Record<string,unknown>; created_at:string}>;
}

export interface Patient {
  id: string; workspace_id: string; first_name: string; last_name: string | null; phone: string | null;
  email: string | null; gender: string | null; birth_date: string | null; preferred_language: string;
  preferred_branch_id: string | null; source: string; source_detail: string | null; status: string;
  marketing_consent: boolean; marketing_consent_at: string | null; last_contact_at: string | null;
  created_at: string; updated_at: string;
}
export interface Appointment {
  id: string; patient_id: string; branch_id: string; doctor_id: string; service_id: string;
  status: string; source: string; start_at: string; end_at: string; duration_minutes: number;
  price_minor: number; currency: string; customer_note: string | null; created_at: string;
}
export interface Branch { id:string; name:string; city:string|null; is_active:boolean; }
export interface Service { id:string; name:string; duration_minutes:number; price_minor:number; currency:string; is_active:boolean; }
export interface Doctor { id:string; staff_id:string; specialization:string|null; is_active:boolean; }
export interface Staff { id:string; first_name:string; last_name:string; is_active:boolean; }

export interface AutomationRule {
  id:string; key:string; name:string; enabled:boolean; trigger_kind:string; offset_minutes:number;
  channel:string; template_name:string; template_language:string; max_lateness_minutes:number;
  config_json:Record<string,unknown>; created_at:string; updated_at:string;
}
export interface AutomationJob {
  id:string; rule_id:string; appointment_id:string; patient_id:string; status:string; scheduled_for:string;
  attempts:number; next_attempt_at:string|null; last_error:string|null; completed_at:string|null; created_at:string;
}
export interface ChannelConnection {
  id:string; channel:string; provider:string; display_name:string; status:string; external_account_id:string|null;
  config_json:Record<string,unknown>; created_at:string; updated_at:string;
}
export interface WorkspaceMember {
  membership_id:string; user_id:string; auth_user_id:string|null; email:string; full_name:string|null;
  role:WorkspaceRole; is_active:boolean;
}
