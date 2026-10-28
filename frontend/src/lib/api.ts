import type { ApiKey, AskResponse, DashboardData, OperatorData, SourceChange, UpdateRuns, FirmProfile, HistoryItem, InventoryRow, ModelOption, ObligationRow, Period, Preset, QuestionFilter, QuestionRow, SearchStrategy, SourceInfo, StreamEvent, TimelineEntry, User } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public retryAfter: number | null = null, // seconds, from a 429's Retry-After header
    public limit: string | null = null, // "questions" or "daily-cost", from a 429's X-Limit header
  ) {
    super(message);
  }
}

/** Called when the backend answers 401 to an account call: the session has ended elsewhere. */
let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (handler: (() => void) | null) => {
  onUnauthorized = handler;
};
const noteUnauthorized = (path: string, status: number) => {
  if (status === 401 && path.startsWith("/api/me")) onUnauthorized?.();
};

async function getJson<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { cache: "no-store" });
  } catch {
    throw new ApiError(0, "unreachable");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    noteUnauthorized(path, response.status);
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : `HTTP ${response.status}`);
  }
  return response.json();
}

export const loadSources = () => getJson<{ sources: SourceInfo[] }>("/api/sources").then((d) => d.sources);
export const loadPresets = () => getJson<{ presets: Preset[] }>("/api/profiles").then((d) => d.presets);
export const loadModels = () =>
  getJson<{ models: ModelOption[]; strategies: SearchStrategy[]; default_strategy: SearchStrategy }>("/api/models");
export const loadHistory = (search = "") =>
  getJson<{ items: HistoryItem[] }>(`/api/history?limit=200&q=${encodeURIComponent(search)}`).then((d) => d.items);
export const loadAnswer = (id: string) =>
  getJson<{ response: AskResponse; obligations: ObligationRow[] | null; changed_sources?: SourceChange[] }>(`/api/history/${id}`).then((d) => ({
    ...d.response,
    obligations: d.obligations,
    changed_sources: d.changed_sources ?? [],
  }));

async function postJson<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "unreachable");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    noteUnauthorized(path, response.status);
    throw new ApiError(response.status, typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
  }
  return response.json();
}

export const extractObligations = (id: string) =>
  postJson<{ rows: ObligationRow[]; cost_usd: number }>(`/api/history/${id}/obligations`, {});
export const loadTimeline = (profile: FirmProfile | null, upcomingOnly: boolean) =>
  postJson<{ entries: TimelineEntry[] }>("/api/timeline", { profile, upcoming_only: upcomingOnly }).then((d) => d.entries);
export const exportUrl = (id: string, format: "md" | "json") => `/api/history/${id}/export?format=${format}`;

/** Asks a question and reports each step as server-sent events arrive. */
export async function askStream(
  body: { question: string; profile: FirmProfile | null; model: string | null; strategy: SearchStrategy | null },
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/ask/stream", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    throw new ApiError(0, "unreachable");
  }
  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => ({}));
    const retryAfter = Number(response.headers.get("retry-after"));
    throw new ApiError(
      response.status,
      typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`,
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
      response.headers.get("x-limit"),
    );
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (line) onEvent(JSON.parse(line.slice(6)) as StreamEvent);
    }
  }
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "unreachable");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    noteUnauthorized(path, response.status);
    throw new ApiError(response.status, typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
  }
  return response.json();
}

// Accounts. The session lives in an httpOnly cookie that the browser sends by itself.
export const loadMe = () => getJson<{ user: User | null }>("/api/auth/me").then((d) => d.user);
export const register = (email: string, password: string, name: string) =>
  send<{ user: User }>("POST", "/api/auth/register", { email, password, name }).then((d) => d.user);
export const login = (email: string, password: string) =>
  send<{ user: User }>("POST", "/api/auth/login", { email, password }).then((d) => d.user);
export const logout = () => send<{ user: null }>("POST", "/api/auth/logout");
export const saveProfile = (profile: FirmProfile | null) =>
  send<{ user: User }>("PUT", "/api/me/profile", { profile }).then((d) => d.user);
export const loadDashboard = (days: Period) => getJson<DashboardData>(`/api/me/dashboard?days=${days}`);
export const deleteAccount = () => send<{ deleted: boolean; answers_removed: number }>("DELETE", "/api/me");
export const loadMyQuestions = (search = "", filter: QuestionFilter = {}) => {
  const params = new URLSearchParams({ q: search });
  for (const [key, value] of Object.entries(filter)) if (value !== undefined && value !== "") params.set(key, String(value));
  return getJson<{ items: QuestionRow[] }>(`/api/me/questions?${params}`).then((d) => d.items);
};
export const loadOperatorOverview = (days: Period) => getJson<OperatorData>(`/api/operator/overview?days=${days}`);
export const loadUpdateRuns = () => getJson<UpdateRuns>("/api/operator/update-runs");
export const startUpdateRun = () => send<{ started: boolean }>("POST", "/api/operator/update-runs");
export const loadMyChanges = () => getJson<{ changes: SourceChange[] }>("/api/me/changes").then((d) => d.changes);
export const loadKeys = () => getJson<{ keys: ApiKey[] }>("/api/me/keys").then((d) => d.keys);
export const createKey = (name: string) => send<{ key: ApiKey; secret: string }>("POST", "/api/me/keys", { name });
export const revokeKey = (id: string) => send<{ revoked: boolean }>("DELETE", `/api/me/keys/${id}`);
export const loadMyObligations = () => getJson<{ rows: InventoryRow[] }>("/api/me/obligations").then((d) => d.rows);
