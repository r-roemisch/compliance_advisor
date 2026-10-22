"use client";

import type { FormEvent } from "react";

import type { Strings } from "@/lib/i18n";

export function Composer(props: {
  t: Strings;
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  const { t, value, busy } = props;
  const tooShort = value.trim().length < 3;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!tooShort && !busy) props.onSubmit();
  };
  return (
    <form onSubmit={submit} className="no-print">
      <label htmlFor="question" className="text-sm font-medium">
        {t.questionLabel}
      </label>
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
        className="mt-1.5 block w-full resize-y rounded border border-line bg-panel px-3 py-2.5 text-[15px] leading-relaxed placeholder:text-ink-3"
      />
      <div className="mt-2 flex items-center gap-4">
        <button
          type="submit"
          disabled={tooShort || busy}
          className="rounded bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:cursor-not-allowed disabled:opacity-45"
        >
          {t.ask}
        </button>
        <span id="question-help" className="text-xs text-ink-3">
          {value.length > 0 && tooShort ? t.tooShort : t.charCount(value.length)} · Ctrl+Enter
        </span>
      </div>
    </form>
  );
}
