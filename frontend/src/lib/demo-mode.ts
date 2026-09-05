import "server-only";

export async function isDemoMode(): Promise<boolean> {
  return process.env.TIA_DEMO_ENABLED === "true";
}
