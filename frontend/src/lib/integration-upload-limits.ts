export const INTEGRATION_UPLOAD_MAX_FILES = 100;
export const INTEGRATION_UPLOAD_MAX_FILE_BYTES = 10 * 1024 * 1024;
export const INTEGRATION_UPLOAD_MAX_TOTAL_BYTES = 50 * 1024 * 1024;
export const INTEGRATION_UPLOAD_MAX_ROWS = 100_000;

export function formatUploadMiB(bytes: number): string {
  return `${Math.floor(bytes / (1024 * 1024))} MB`;
}

export function integrationUploadLimitError(
  files: readonly { name: string; size: number }[],
): string | null {
  if (files.length > INTEGRATION_UPLOAD_MAX_FILES) {
    return `الحد الأقصى ${INTEGRATION_UPLOAD_MAX_FILES} ملف في جلسة واحدة.`;
  }
  for (const file of files) {
    if (file.size > INTEGRATION_UPLOAD_MAX_FILE_BYTES) {
      return `${file.name}: الحد الأقصى للملف ${formatUploadMiB(INTEGRATION_UPLOAD_MAX_FILE_BYTES)}.`;
    }
  }
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
  if (totalBytes > INTEGRATION_UPLOAD_MAX_TOTAL_BYTES) {
    return `إجمالي الملفات يتجاوز ${formatUploadMiB(INTEGRATION_UPLOAD_MAX_TOTAL_BYTES)} للجلسة الواحدة.`;
  }
  return null;
}
