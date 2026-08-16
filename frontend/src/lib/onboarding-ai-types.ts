export type OnboardingAIResponse = {
  session_id: string;
  status: string;
  version: number;
  assistant_message: string;
  capabilities: string[];
  missing_information: string[];
  plan: Record<string, unknown> | null;
  plan_summary: {
    branches?: number;
    services?: number;
    doctors?: number;
    branch_schedules?: number;
    doctor_schedules?: number;
    booking_settings?: boolean;
  };
  execution_result: Record<string, unknown>;
  requires_confirmation: boolean;
  readiness_refresh_required: boolean;
};

export type OnboardingAIActionState = {
  response: OnboardingAIResponse | null;
  error: string | null;
};

export const initialOnboardingAIActionState: OnboardingAIActionState = {
  response: null,
  error: null,
};
