"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { exportUrl } from "@/lib/api";
import type { Strings } from "@/lib/i18n";
import type { AskResponse, Lang } from "@/lib/types";
import { LayerStrip } from "./LayerStrip";

/** Turns citations into links the renderer shows as chips: "[2]", "[1, 3]", "[1, Art. 32 Abs. 1]". */
export function linkCitations(answer: string, available: number): string {
  return answer.replace(/\[([^[\]]*)\]/g, (whole, inner: string) => {
    const parts = inner.split(/([,;])/);
    let numeric = 0;
    const linked = parts.map((part) => {
      const n = Number(part.trim());
      if (/^\s*\d+\s*$/.test(part) && n >= 1 && n <= available) {
        numeric += 1;
        return `[${n}](#cite-${n})`;
      }
      return part;
    });
    if (numeric === 0) return whole;
    const meaningful = parts.filter((p) => p.trim() && !/^[,;]$/.test(p.trim())).length;
    return numeric === meaningful ? linked.filter((p) => !/^[,;]$/.test(p.trim())).join("") : `[${linked.join("")}]`;
  });
}

export function AnswerView(props: {
  t: Strings;
  lang: Lang;
  result: AskResponse;
  active: number | null;
  onCite: (n: number) => void;
  onHover: (n: number | null) => void;
}) {
  const { t, lang, result } = props;
  const kinds = result.redactions.map((k) => t.redactionKinds[k] ?? k).join(", ");
  const cost = result.usage.cost_usd > 0 ? t.cost(result.usage.cost_usd < 0.01 ? result.usage.cost_usd.toFixed(4) : result.usage.cost_usd.toFixed(3)) : null;

  return (
    <section aria-labelledby="answer-title" className="rounded-xl border border-line bg-panel">
      <div className="px-5 pb-5 pt-4">
        <p className="mb-4 border-b border-line pb-3 text-sm text-ink-2">{result.question}</p>
        {result.redactions.length > 0 && (
          <p role="note" className="mb-3 rounded-lg bg-panel-2 px-3 py-2 text-sm text-ink-2">
            {t.redacted(kinds)}
          </p>
        )}
        {(result.coverage === "none" || result.coverage === "partial") && (
          <p
            role="note"
            className={`mb-4 rounded-lg bg-amber-soft px-3 py-2 text-sm font-medium ${result.coverage === "none" ? "text-amber" : "text-ink"}`}
          >
            {result.coverage === "none" ? t.coverageNone : t.coveragePartial}
          </p>
        )}
        <h2 id="answer-title" className="sr-only">
          {t.answer}
        </h2>
        <div className="answer">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children }) => {
                const match = href?.match(/^#cite-(\d+)$/);
                if (!match) {
                  return (
                    <a href={href} target="_blank" rel="noreferrer">
                      {children}
                    </a>
                  );
                }
                const n = Number(match[1]);
                return (
                  <button
                    type="button"
                    onClick={() => props.onCite(n)}
                    onMouseEnter={() => props.onHover(n)}
                    onMouseLeave={() => props.onHover(null)}
                    onFocus={() => props.onHover(n)}
                    onBlur={() => props.onHover(null)}
                    aria-label={`${t.passages} ${n}`}
                    className={`mx-[1px] inline-flex h-[1.25rem] min-w-[1.25rem] translate-y-[-1px] items-center justify-center rounded-md border px-1 align-middle text-[11px] font-semibold tabular-nums ${
                      props.active === n ? "border-accent bg-accent text-accent-ink" : "border-accent/50 text-accent hover:bg-accent-soft"
                    }`}
                  >
                    {n}
                  </button>
                );
              },
            }}
          >
            {linkCitations(result.answer, result.passages.length)}
          </ReactMarkdown>
        </div>
        <LayerStrip passages={result.passages} cited={result.cited} lang={lang} label={t.layersUsed} />
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line px-5 py-2.5 text-xs text-ink-2">
        <span>{result.model}</span>
        <span className="tabular-nums">{t.tokens(result.usage.input_tokens, result.usage.output_tokens)}</span>
        {cost && <span className="tabular-nums">{cost}</span>}
        {result.id && (
          <span className="no-print ml-auto flex flex-wrap items-center gap-2">
            <span>{t.export}:</span>
            <a className="btn btn-outline btn-sm" href={exportUrl(result.id, "md")}>
              {t.exportMd}
            </a>
            <a className="btn btn-outline btn-sm" href={exportUrl(result.id, "json")}>
              {t.exportJson}
            </a>
            <button type="button" onClick={() => window.print()} className="btn btn-outline btn-sm">
              {t.print}
            </button>
          </span>
        )}
      </div>
    </section>
  );
}
