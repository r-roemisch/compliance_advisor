"use client";

import { useEffect, useState } from "react";

import { TOOL_NAMES, type Strings } from "@/lib/i18n";
import type { Lang, Stage } from "@/lib/types";

/** The real steps the backend reports while it works; tools appear only when called. */
export function Progress({
  t,
  lang,
  stage,
  tools,
  found,
  profileSet,
  draft,
}: {
  t: Strings;
  lang: Lang;
  stage: Stage;
  tools: string[];
  found: { count: number; sources: string[] } | null;
  profileSet: boolean;
  draft: string;
}) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.round((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);

  const steps: { id: Stage; label: string }[] = [
    { id: "search", label: t.stageSearch },
    { id: "model", label: t.stageModel },
    ...(tools.length || stage === "tools" || stage === "writing" ? [{ id: "tools" as Stage, label: t.stageTools }] : []),
    { id: "writing", label: t.stageWriting },
  ];
  const order: Stage[] = ["search", "model", "tools", "writing"];
  const position = order.indexOf(stage);

  return (
    <div role="status" aria-live="polite" className="rounded border border-line bg-panel px-4 py-3">
      <ol className="flex flex-col gap-1.5 text-sm">
        {steps.map((step) => {
          const index = order.indexOf(step.id);
          const state = index < position ? "done" : index === position ? "active" : "todo";
          return (
            <li key={step.id} className={`flex items-center gap-2.5 ${state === "todo" ? "text-ink-3" : ""}`}>
              <span
                aria-hidden
                className={`inline-block h-2.5 w-2.5 rounded-full border ${
                  state === "done" ? "border-ink bg-ink" : state === "active" ? "animate-pulse border-accent bg-accent" : "border-line"
                }`}
              />
              <span className={state === "active" ? "font-medium" : ""}>{step.label}</span>
              {step.id === "tools" && tools.length > 0 && (
                <span className="text-ink-2">({tools.map((n) => TOOL_NAMES[n]?.[lang] ?? n).join(", ")})</span>
              )}
              {step.id === "search" && found && (
                <span className="text-ink-2">: {t.found(found.count, found.sources.join(", "))}</span>
              )}
              {step.id === "model" && profileSet && state !== "todo" && (
                <span className="text-ink-2">: {t.profileUsed}</span>
              )}
            </li>
          );
        })}
      </ol>
      <p className="mt-2 text-xs text-ink-3 tabular-nums">{t.elapsed(seconds)}</p>
      {draft && (
        <div className="answer mt-3 border-t border-line pt-3 text-ink-2" aria-live="off">
          <p className="whitespace-pre-wrap">
            {draft.replace(/\s*[*_]*\s*Coverage:.*$/i, "")}
            <span aria-hidden className="ml-0.5 inline-block h-4 w-[2px] translate-y-[3px] animate-pulse bg-accent" />
          </p>
        </div>
      )}
    </div>
  );
}
