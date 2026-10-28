// Per-browser conveniences only (language, theme, Firm Profile, model). Storage can be
// unavailable (private windows, blocked site data), so every access is guarded.

import { ACTIVITIES, CUSTOMERS, FIRM_TYPES, SIZES } from "./i18n";
import type { FirmProfile } from "./types";

export function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(`ca.${key}`);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

/** A Firm Profile read from storage or the account, kept only if every value still exists;
 *  a renamed firm type or activity would otherwise make every question fail. */
export function validProfile(value: unknown): FirmProfile | null {
  if (!value || typeof value !== "object") return null;
  const p = value as Partial<FirmProfile>;
  if (!p.firm_type || !(p.firm_type in FIRM_TYPES)) return null;
  if (!p.size || !(p.size in SIZES) || !p.customers || !(p.customers in CUSTOMERS)) return null;
  return { firm_type: p.firm_type, size: p.size, customers: p.customers, activities: (p.activities ?? []).filter((a) => a in ACTIVITIES) };
}

export function writeStored(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(`ca.${key}`, JSON.stringify(value));
  } catch {
    /* not stored; the setting still applies for this visit */
  }
}
