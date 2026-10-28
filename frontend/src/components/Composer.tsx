"use client";

import type { FormEvent } from "react";

import type { Strings } from "@/lib/i18n";
import type { Lang, ModelOption, SearchStrategy } from "@/lib/types";

export function Composer(props: {
  t: Strings;
  lang: Lang;
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
  models: ModelOption[];
  model: string;
  onModel: (id: string) => void;
  strategies: SearchStrategy[];
  strategy: SearchStrategy;
  onStrategy: (s: SearchStrategy) => void;
}) {
  const { t, value, busy, models, model } = props;
  const tooShort = value.trim().length < 3;
  const current = models.find((m) => m.id === model);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!tooShort && !busy) props.onSubmit();
  };
  return (
    <form onSubmit={submit} className="no-print">
      <label htmlFor="question" className="sr-only">
        {t.questionLabel}
      </label>
      {/* The one raised element on the page: where every piece of work starts. */}
      <div className="rounded-2xl border border-line bg-panel shadow-raise transition-[border-color,box-shadow] focus-within:border-accent focus-within:ring-[3px] focus-within:ring-accent-soft">
        <textarea
          id="question"
          value={value}
          onChange={(e) => props.onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e);
          }}
          rows={3}
          maxLength={2000}
          placeholder={t.questionPlaceholder}
          aria-describedby="question-help"
          className="block max-h-72 min-h-[5.5rem] w-full resize-none bg-transparent px-4 pb-2 pt-3.5 text-[15px] leading-relaxed [field-sizing:content] placeholder:text-ink-3 focus-visible:outline-none"
        />
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 pb-3">
          <span className="relative inline-flex" title={current?.note?.[props.lang]}>
            <select
              value={model}
              onChange={(e) => props.onModel(e.target.value)}
              aria-label={t.model}
              className="chip max-w-[15rem] cursor-pointer appearance-none truncate py-1 pr-7 text-[13px] text-ink-2"
            >
              {models.length === 0 && <option value="">…</option>}
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                  {m.eu_hosted ? ` (${t.euHosted})` : ""}
                </option>
              ))}
            </select>
            <svg aria-hidden width="10" height="10" viewBox="0 0 10 10" className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-ink-3">
              <path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          {props.strategies.length > 1 && (
            <span className="relative inline-flex" title={t.strategyNotes[props.strategy]}>
              <select
                value={props.strategy}
                onChange={(e) => props.onStrategy(e.target.value as SearchStrategy)}
                aria-label={t.strategy}
                className="chip max-w-[15rem] cursor-pointer appearance-none truncate py-1 pr-7 text-[13px] text-ink-2"
              >
                {props.strategies.map((s) => (
                  <option key={s} value={s}>
                    {t.strategies[s]}
                  </option>
                ))}
              </select>
              <svg aria-hidden width="10" height="10" viewBox="0 0 10 10" className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-ink-3">
                <path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
          )}
          <span id="question-help" className="mr-auto flex flex-wrap items-center gap-x-3 text-xs text-ink-3 tabular-nums">
            <span>{value.length > 0 && tooShort ? t.tooShort : t.charCount(value.length)}</span>
            <span className="hidden sm:inline">
              <kbd className="kbd">Ctrl</kbd> + <kbd className="kbd">Enter</kbd>
            </span>
          </span>
          <button type="submit" disabled={tooShort || busy} className="btn btn-primary ml-auto">
            {t.ask}
          </button>
        </div>
      </div>
    </form>
  );
}
