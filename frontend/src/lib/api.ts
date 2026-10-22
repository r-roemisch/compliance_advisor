import type { AskResponse, FirmProfile, HistoryItem, ModelOption, Preset, SourceInfo, StreamEvent } from "./types";

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
export const loadHistory = () => getJson<{ items: HistoryItem[] }>("/api/history").then((d) => d.items);
export const loadAnswer = (id: string) =>
  getJson<{ response: AskResponse }>(`/api/history/${id}`).then((d) => ({ ...d.response, id }));
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
