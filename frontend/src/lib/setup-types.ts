export interface SetupBranch {
  id:string; name:string; code:string; phone:string|null; email:string|null;
  address_line1:string|null; city:string|null; timezone:string|null; is_active:boolean;
}
export interface SetupService {
  id:string; name:string; slug:string; category:string|null; duration_minutes:number;
  buffer_before_minutes:number; buffer_after_minutes:number; price_minor:number;
  currency:string; requires_medical_review:boolean; is_active:boolean;
}
export interface SetupStaff {
  id:string; first_name:string; last_name:string; email:string|null; phone:string|null;
  job_title:string|null; is_active:boolean;
}
export interface SetupDoctor {
  id:string; staff_id:string; staff_name:string; specialization:string|null;
  booking_enabled:boolean; is_active:boolean;
}
export interface DoctorBranchAssignment { id:string; doctor_id:string; branch_id:string; is_primary:boolean; is_active:boolean; }
export interface DoctorServiceAssignment { id:string; doctor_id:string; service_id:string; custom_duration_minutes:number|null; custom_price_minor:number|null; is_active:boolean; }
export interface WorkingHour { id:string; weekday:number; start_time:string; end_time:string; branch_id:string; doctor_id?:string; }
export interface BookingSettings {
  slot_interval_minutes:number; minimum_notice_minutes:number; booking_horizon_days:number;
  cancellation_notice_minutes:number; allow_same_day_booking:boolean; require_confirmation:boolean; default_currency:string;
}
export interface ClinicSetupSnapshot {
  workspace_id:string; workspace_name:string; workspace_slug:string; workspace_timezone:string;
  branches:SetupBranch[]; services:SetupService[]; staff:SetupStaff[]; doctors:SetupDoctor[];
  doctor_branches:DoctorBranchAssignment[]; doctor_services:DoctorServiceAssignment[];
  branch_working_hours:WorkingHour[]; doctor_working_hours:WorkingHour[];
  booking_settings:BookingSettings|null;
  readiness:{ready:boolean;progress_percent:number;completed_steps:number;total_steps:number;checks:Record<string,boolean>;missing:string[]};
}
