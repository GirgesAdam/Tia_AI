/**
 * Deprecated compatibility shim.
 *
 * Analytics is catalog-first from v0.47.0 and the dashboard no longer mounts
 * a natural-language assistant. Keep this inert export for patch-overwrite and
 * older imports so incremental ZIP application cannot leave a stale AI UI file
 * that fails TypeScript checks.
 */
export function AnalyticsAssistant() {
  return null;
}
