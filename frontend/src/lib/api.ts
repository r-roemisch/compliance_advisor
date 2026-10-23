import type { AskResponse, DashboardData, FirmProfile, HistoryItem, InventoryRow, ModelOption, ObligationRow, Preset, QuestionRow, SourceInfo, StreamEvent, TimelineEntry, User } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function getJson<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { cache: "no-store" });
  } catch {
    throw new ApiError(0, "unreachable");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : `HTTP ${response.status}`);
  }
  return response.json();
}

export const loadSources = () => getJson<{ sources: SourceInfo[] }>("/api/sources").then((d) => d.sources);
export const loadPresets = () => getJson<{ presets: Preset[] }>("/api/profiles").then((d) => d.presets);
export const loadModels = () => getJson<{ models: ModelOption[] }>("/api/models").then((d) => d.models);
export const loadHistory = (search = "") =>
  getJson<{ items: HistoryItem[] }>(`/api/history?limit=200&q=${encodeURIComponent(search)}`).then((d) => d.items);
export const loadAnswer = (id: string) =>
  getJson<{ response: AskResponse; obligations: ObligationRow[] | null }>(`/api/history/${id}`).then((d) => ({
    ...d.response,
    id,
    obligations: d.obligations,
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
    throw new ApiError(response.status, typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
  }
  return response.json();
}

export const extractObligations = (id: string) =>
  postJson<{ rows: ObligationRow[] }>(`/api/history/${id}/obligations`, {}).then((d) => d.rows);
export const loadTimeline = (profile: FirmProfile | null, upcomingOnly: boolean) =>
  postJson<{ entries: TimelineEntry[] }>("/api/timeline", { profile, upcoming_only: upcomingOnly }).then((d) => d.entries);
export const exportUrl = (id: string, format: "md" | "json") => `/api/history/${id}/export?format=${format}`;

/** Asks a question and reports each step as server-sent events arrive. */
export async function askStream(
  body: { question: string; profile: FirmProfile | null; model: string | null },
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
    throw new ApiError(response.status, typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
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
export const loadDashboard = () => getJson<DashboardData>("/api/me/dashboard");
export const deleteAccount = () => send<{ deleted: boolean; answers_removed: number }>("DELETE", "/api/me");
export const loadMyQuestions = (search = "") =>
  getJson<{ items: QuestionRow[] }>(`/api/me/questions?q=${encodeURIComponent(search)}`).then((d) => d.items);
export const loadMyObligations = () => getJson<{ rows: InventoryRow[] }>("/api/me/obligations").then((d) => d.rows);
