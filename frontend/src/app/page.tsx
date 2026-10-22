"use client";

// Bare step 1 page: proves the pipeline end to end. The real layout comes in step 2.

import { useEffect, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { AskResponse, Preset, SourcesResponse } from "@/lib/types";

const NOTICE =
  "This is regulatory information generated from the indexed Sources, not legal advice. " +
  "Verify against the official text before relying on it.";

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : `Error ${response.status}`;
  } catch {
    return `Error ${response.status}: the backend is not reachable`;
  }
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sources, setSources] = useState<SourcesResponse | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [presetId, setPresetId] = useState("");

  useEffect(() => {
    fetch("/api/sources")
      .then(async (r) => (r.ok ? setSources(await r.json()) : setError(await readError(r))))
      .catch(() => setError("The backend is not reachable"));
    fetch("/api/profiles")
      .then(async (r) => r.ok && setPresets((await r.json()).presets))
      .catch(() => undefined);
  }, []);

  async function ask(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question,
          profile: presets.find((p) => p.id === presetId)?.profile ?? null,
        }),
      });
      if (response.ok) setResult(await response.json());
      else setError(await readError(response));
    } catch {
      setError("The backend is not reachable");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-4">
      <h1 className="text-2xl font-semibold">Compliance Advisor</h1>

      <form onSubmit={ask} className="flex flex-col gap-2">
        <label htmlFor="question" className="text-sm">
          Your question (English or German)
        </label>
        <textarea
          id="question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder="When is an ICT-related incident major under DORA?"
          className="rounded border p-2"
        />
        <label htmlFor="profile" className="text-sm">
          Firm Profile
        </label>
        <select
          id="profile"
          value={presetId}
          onChange={(e) => setPresetId(e.target.value)}
          className="self-start rounded border p-1"
        >
          <option value="">No Firm Profile</option>
          {presets.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label.en}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={loading || question.trim().length < 3}
          className="self-start rounded border px-4 py-1 disabled:opacity-50"
        >
          Ask
        </button>
      </form>

      {loading && <p role="status">Searching the Sources and writing the answer… this can take up to 30 seconds.</p>}
      {error && <p role="alert" className="text-red-600">{error}</p>}

      {result && (
        <section className="flex flex-col gap-4">
          {result.redactions.length > 0 && (
            <p role="note" className="text-sm">
              Removed before sending: {result.redactions.join(", ")}.
            </p>
          )}
          <h2 className="text-lg font-semibold">Answer</h2>
          <div className="prose-like flex flex-col gap-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.answer}</ReactMarkdown>
          </div>
          <p className="text-xs">
            {result.model} · {result.usage.input_tokens} tokens in, {result.usage.output_tokens} tokens out
          </p>

          {result.tools.length > 0 && (
            <>
              <h2 className="text-lg font-semibold">Rule checks</h2>
              {result.tools.map((t, i) => (
                <details key={i} className="rounded border p-2 text-sm">
                  <summary>
                    {t.name}:{" "}
                    {String(t.result.major ?? t.result.risk_class ?? "")}
                  </summary>
                  <pre className="overflow-x-auto whitespace-pre-wrap text-xs">
                    {JSON.stringify(t.result, null, 2)}
                  </pre>
                </details>
              ))}
            </>
          )}

          <h2 className="text-lg font-semibold">Passages</h2>
          <ol className="flex flex-col gap-3">
            {result.passages.map((p) => (
              <li key={p.passage_id} className="rounded border p-2 text-sm">
                <div>
                  <strong>[{p.n}]</strong> {p.provision || p.short_title} · {p.issuer} · {p.layer} ·{" "}
                  {p.legal_status} · as of {p.as_of} · score {p.score.toFixed(2)}
                  {result.cited.includes(p.n) ? " · cited" : " · not cited"}{" "}
                  <a href={p.link || p.url} target="_blank" rel="noreferrer" className="underline">
                    open provision
                  </a>
                </div>
                <p className="mt-1 whitespace-pre-line">{p.text}</p>
              </li>
            ))}
          </ol>
        </section>
      )}

      {sources && (
        <section className="text-sm">
          <h2 className="text-lg font-semibold">Sources in the Corpus</h2>
          <ul>
            {sources.sources.map((s) => (
              <li key={s.id}>
                {s.short_title} ({s.issuer}, {s.layer}): {s.passages} Passages
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer className="mt-auto border-t pt-2 text-xs">{NOTICE}</footer>
    </main>
  );
}
