import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Create a UUID-shaped id for client-side idempotency keys.
 *
 * Some browser/webview runtimes expose `crypto` without `randomUUID()`.
 * Prefer the native implementation, then `getRandomValues()`, and only use
 * Math.random as a last compatibility fallback. These ids are request
 * deduplication keys, not authentication or secret material.
 */
export function createClientRequestId(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }

  const bytes = new Uint8Array(16);
  if (cryptoApi && typeof cryptoApi.getRandomValues === "function") {
    cryptoApi.getRandomValues(bytes);
  } else {
    const now = Date.now();
    for (let index = 0; index < bytes.length; index += 1) {
      const timeByte = (now >>> ((index % 4) * 8)) & 0xff;
      bytes[index] = (Math.floor(Math.random() * 256) ^ timeByte) & 0xff;
    }
  }

  // RFC 4122 / UUID v4 version + variant bits.
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10, 16).join("")}`;
}
