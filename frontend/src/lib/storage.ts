// Per-browser conveniences only (language, theme, Firm Profile, model). Storage can be
// unavailable (private windows, blocked site data), so every access is guarded.

export function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(`ca.${key}`);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeStored(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(`ca.${key}`, JSON.stringify(value));
  } catch {
    /* not stored; the setting still applies for this visit */
  }
}
