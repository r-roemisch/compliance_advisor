"use client";

import { useState } from "react";

import { LEGAL_STATUS, REGIMES, type Strings } from "@/lib/i18n";
import type { HistoryItem, Lang, SourceInfo } from "@/lib/types";
import { LayerGlyph, layerName } from "./LayerGlyph";

export function Sidebar(props: {
  t: Strings;
  lang: Lang;
  history: HistoryItem[];
  sources: SourceInfo[];
  currentId: string | null;
  onOpen: (id: string) => void;
  onNew: () => void;
}) {
  const { t, lang, history, sources } = props;
  const [tab, setTab] = useState<"history" | "sources">("history");
  const fmt = new Intl.DateTimeFormat(lang === "de" ? "de-DE" : "en-GB", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  const byRegime = Object.keys(REGIMES)
    .map((regime) => ({ regime, items: sources.filter((s) => s.regime === regime) }))
    .filter((g) => g.items.length > 0);

  return (
    <aside className="no-print order-2 flex flex-col gap-3 lg:order-none lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)]">
      <button
        type="button"
        onClick={props.onNew}
        className="rounded border border-line bg-panel px-3 py-2 text-left text-sm font-medium hover:border-accent"
      >
        {t.newQuestion}
      </button>
      <div role="tablist" className="flex border-b border-line text-sm">
        {(["history", "sources"] as const).map((id) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`-mb-px border-b-2 px-3 py-1.5 ${tab === id ? "border-ink font-medium" : "border-transparent text-ink-2"}`}
          >
            {id === "history" ? t.history : t.sources}
          </button>
        ))}
      </div>

      <div role="tabpanel" className="min-h-0 overflow-y-auto pr-1">
        {tab === "history" ? (
          history.length === 0 ? (
            <p className="text-sm text-ink-3">{t.historyEmpty}</p>
          ) : (
            <ul className="flex flex-col">
              {history.map((h) => (
                <li key={h.id}>
                  <button
                    type="button"
                    onClick={() => props.onOpen(h.id)}
                    aria-current={props.currentId === h.id}
                    className={`w-full rounded px-2 py-2 text-left text-sm hover:bg-panel ${
                      props.currentId === h.id ? "bg-panel" : ""
                    }`}
                  >
                    <span className="line-clamp-2">{h.question}</span>
                    <span className="mt-0.5 block text-xs text-ink-3 tabular-nums">{fmt.format(new Date(h.created_at))}</span>
                  </button>
                </li>
              ))}
            </ul>
          )
        ) : (
          <div className="flex flex-col gap-4">
            {byRegime.map((g) => (
              <section key={g.regime}>
                <h3 className="mb-1 text-xs font-semibold text-ink-2">{REGIMES[g.regime][lang]}</h3>
                <ul className="flex flex-col gap-2">
                  {g.items.map((s) => (
                    <li key={s.id} className="text-sm">
                      <a href={s.url} target="_blank" rel="noreferrer" className="flex items-start gap-2 hover:text-accent">
                        <span className="mt-0.5">
                          <LayerGlyph layer={s.layer} lang={lang} size={14} />
                        </span>
                        <span>
                          <span className="provision">{s.short_title}</span>
                          <span className="block text-xs text-ink-3">
                            {layerName(s.layer, lang)}, {s.version || LEGAL_STATUS[s.legal_status]?.[lang]}
                            {s.legal_status !== "in_force" && `, ${LEGAL_STATUS[s.legal_status]?.[lang]}`}
                          </span>
                          <span className="block text-xs text-ink-3">
                            {t.asOf(s.as_of)}, {t.passagesCount(s.passages)}
                          </span>
                        </span>
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
