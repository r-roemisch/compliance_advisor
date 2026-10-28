"use client";

import { useState } from "react";

import { TOOL_NAMES, type Strings } from "@/lib/i18n";
import type { AskResponse, Lang, TraceHit } from "@/lib/types";

type StepId = "precheck" | "named" | "vector" | "keyword" | "merged" | "cap" | "passages" | "tools" | "model";

/** The Answer Trace: every step from question to answer, as a flow of chips with the numbers;
 *  each chip opens what happened in that step. Stored with the answer, so it reopens from history. */
export function AnswerTrace({ t, lang, result }: { t: Strings; lang: Lang; result: AskResponse }) {
  const [open, setOpen] = useState<StepId | null>(null);
  const trace = result.trace;
  if (!trace) return null;
  const hybrid = trace.strategy === "hybrid";
  const byId = new Map(result.passages.map((p) => [p.passage_id, p]));
  const seconds = trace.seconds ?? {};

  const hitList = (hits: TraceHit[], withRank = false) => (
    <ol className="columns-1 gap-x-6 text-sm sm:columns-2">
      {hits.map((h, i) => {
        const p = byId.get(h.passage_id);
        return (
          <li key={`${h.passage_id}-${i}`} className="flex items-baseline gap-2 py-0.5">
            <span className="w-5 shrink-0 text-right text-ink-3 tabular-nums">{withRank ? (h.rank ?? i + 1) : i + 1}</span>
            <span className={p ? "font-medium" : "text-ink-2"}>{h.provision || h.short_title}</span>
            {p && <span className="text-xs text-accent tabular-nums">[{p.n}]</span>}
            {h.score != null && <span className="ml-auto text-xs text-ink-3 tabular-nums">{h.score.toFixed(3)}</span>}
          </li>
        );
      })}
    </ol>
  );

  const steps: { id: StepId; label: string; value: string; details: React.ReactNode }[] = [
    {
      id: "precheck",
      label: t.tracePreCheck,
      value: result.redactions.length ? t.traceRemoved(result.redactions.length) : t.traceNothingRemoved,
      details: (
        <p className="text-sm">
          {result.redactions.length ? result.redactions.map((k) => t.redactionKinds[k] ?? k).join(", ") : t.traceNothingRemovedLong}
        </p>
      ),
    },
    ...(trace.named.length
      ? [
          {
            id: "named" as StepId,
            label: t.traceNamed,
            value: t.traceProvisions(trace.named.length),
            details: (
              <div className="text-sm">
                <p className="mb-1 text-ink-2">{trace.named.join(", ")}</p>
                {hitList(trace.named_hits)}
              </div>
            ),
          },
        ]
      : []),
    { id: "vector", label: t.traceVector, value: t.traceCandidates(trace.vector.length), details: hitList(trace.vector) },
    ...(hybrid
      ? [
          { id: "keyword" as StepId, label: t.traceKeyword, value: t.traceCandidates(trace.keyword.length), details: hitList(trace.keyword, true) },
          {
            id: "merged" as StepId,
            label: t.traceMerged,
            value: t.traceCandidates(trace.merged.length),
            details: <p className="text-sm text-ink-2">{t.traceMergedLong}</p>,
          },
        ]
      : []),
    ...(trace.max_per_source
      ? [
          {
            id: "cap" as StepId,
            label: t.traceCap(trace.max_per_source),
            value: t.traceHeldBack(trace.capped_out),
            details: <p className="text-sm text-ink-2">{t.traceCapLong(trace.max_per_source)}</p>,
          },
        ]
      : []),
    {
      id: "passages",
      label: t.passages,
      value: String(result.passages.length),
      details: (
        <ol className="text-sm">
          {result.passages.map((p) => (
            <li key={p.n} className="flex flex-wrap items-baseline gap-x-2 py-0.5">
              <span className="w-5 shrink-0 text-right text-accent tabular-nums">[{p.n}]</span>
              <span className="font-medium">{p.provision}</span>
              <span className="text-xs text-ink-3">{t.traceFoundBy[trace.found_by[p.passage_id] ?? "vector"]}</span>
              <span className="ml-auto text-xs text-ink-3 tabular-nums">{p.score.toFixed(3)}</span>
            </li>
          ))}
        </ol>
      ),
    },
    ...(result.tools.length
      ? [
          {
            id: "tools" as StepId,
            label: t.traceTools,
            value: String(result.tools.length),
            details: <p className="text-sm">{result.tools.map((r) => TOOL_NAMES[r.name]?.[lang] ?? r.name).join(", ")}</p>,
          },
        ]
      : []),
    {
      id: "model",
      label: t.traceModel,
      value: result.model.split("/").pop() ?? result.model,
      details: (
        <p className="text-sm tabular-nums">
          {t.tokens(result.usage.input_tokens, result.usage.output_tokens)}
          {result.usage.cost_usd > 0 && ` · ${t.cost(result.usage.cost_usd < 0.01 ? result.usage.cost_usd.toFixed(4) : result.usage.cost_usd.toFixed(3))}`}
          {seconds.answer != null && ` · ${t.traceSeconds(seconds.answer)}`}
        </p>
      ),
    },
  ];
  const current = steps.find((s) => s.id === open);

  return (
    <div className="mt-4 border-t border-line pt-3">
      <p className="mb-2 flex flex-wrap items-baseline gap-x-3 text-xs text-ink-2">
        <span>{t.traceTitle}</span>
        <span className="text-ink-3">{t.strategies[trace.strategy as "vector" | "hybrid"] ?? trace.strategy}</span>
        {seconds.total != null && <span className="text-ink-3 tabular-nums">{t.traceSeconds(seconds.total)}</span>}
      </p>
      <ol className="flex flex-wrap items-center gap-y-2">
        {steps.map((step, i) => (
          <li key={step.id} className="flex items-center">
            {i > 0 && (
              <svg aria-hidden width="14" height="10" viewBox="0 0 14 10" className="mx-1 shrink-0 text-ink-3">
                <path d="M1 5h11M8 1.5 12 5 8 8.5" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
            <button
              type="button"
              onClick={() => setOpen(open === step.id ? null : step.id)}
              aria-expanded={open === step.id}
              className={`chip py-1 text-[13px] ${open === step.id ? "border-accent bg-accent-soft text-ink" : "text-ink-2"}`}
            >
              <span>{step.label}</span>
              <span className="ml-1.5 font-semibold tabular-nums">{step.value}</span>
            </button>
          </li>
        ))}
      </ol>
      {current && (
        <div className="mt-2 rounded-lg bg-panel-2 px-3 py-2">
          <p className="mb-1 text-xs font-medium text-ink-2">{current.label}</p>
          {current.details}
        </div>
      )}
    </div>
  );
}
