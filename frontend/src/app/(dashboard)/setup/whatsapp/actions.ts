"use server";

import { revalidatePath } from "next/cache";

import { tiaRequest } from "@/lib/tia/api";

export type EmbeddedSignupPayload = {
  code: string;
  waba_id: string;
  phone_number_id: string;
  business_id?: string | null;
};

export type WhatsAppSetupState = {
  connected: boolean;
  connection_status: "active" | "paused" | "disconnected" | null;
  display_phone_number: string | null;
  verified_name: string | null;
  provider_health_state: string | null;
  provider_error_code: string | null;
  provider_error: string | null;
  embedded_signup_available: boolean;
  provider_credentials_ready: boolean;
  transport_ready: boolean;
  templates_ready: boolean;
  ready_for_automations: boolean;
  admin_action: "connect_meta" | "resolve_meta_restriction" | "wait_for_template_review" | "none";
  admin_message: string | null;
  system_message: string | null;
};

export async function completeWhatsAppEmbeddedSignupAction(
  payload: EmbeddedSignupPayload,
): Promise<{ state: WhatsAppSetupState }> {
  const result = await tiaRequest<{ state: WhatsAppSetupState }>(
    "/channels/whatsapp/setup/embedded-signup/complete",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
  revalidatePath("/setup/whatsapp");
  revalidatePath("/automations");
  return result;
}
