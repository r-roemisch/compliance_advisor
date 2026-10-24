"use client";

import { useState } from "react";

import { LEGAL_STATUS, REGIMES, type Strings } from "@/lib/i18n";
import type { FirmProfile, HistoryItem, Lang, SourceInfo } from "@/lib/types";
import { LayerGlyph, layerName } from "./LayerGlyph";
import { TimelinePanel } from "./TimelinePanel";

type Group = { label: string; recent: boolean; items: HistoryItem[] };

/** Today, yesterday and earlier, by the browser's own calendar day. */
function groupByDay(history: HistoryItem[], t: Strings): Group[] {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);
  const groups: Group[] = [
    { label: t.today, recent: true, items: [] },
    { label: t.yesterday, recent: true, items: [] },
    { label: t.earlier, recent: false, items: [] },
  ];
  for (const h of history) {
    const at = new Date(h.created_at);
    groups[at >= startOfToday ? 0 : at >= startOfYesterday ? 1 : 2].items.push(h);
  }
  return groups.filter((g) => g.items.length > 0);
}

export function Sidebar(props: {
  t: Strings;
  lang: Lang;
  history: HistoryItem[];
  sources: SourceInfo[];
  currentId: string | null;
  profile: FirmProfile | null;
  onOpen: (id: string) => void;
  onNew: () => void;
}) {
  const { t, lang, history, sources } = props;
  const [tab, setTab] = useState<"history" | "timeline" | "sources">("history");
  const locale = lang === "de" ? "de-DE" : "en-GB";
  const timeFmt = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" });
  const fullFmt = new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  const byRegime = Object.keys(REGIMES)
    .map((regime) => ({ regime, items: sources.filter((s) => s.regime === regime) }))
    .filter((g) => g.items.length > 0);

  return (
    <aside className="no-print order-2 flex flex-col gap-3 lg:order-none lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)]">
      <button type="button" onClick={props.onNew} className="btn btn-outline justify-start py-2">
        <svg aria-hidden width="14" height="14" viewBox="0 0 14 14" className="text-accent">
          <path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
        {t.newQuestion}
      </button>
      <div role="tablist" className="switch text-sm">
        {(["history", "timeline", "sources"] as const).map((id) => (
          <button key={id} role="tab" type="button" aria-selected={tab === id} onClick={() => setTab(id)} className="flex-1 px-2 text-center">
            {id === "history" ? t.history : id === "timeline" ? t.timeline : t.sources}
          </button>
        ))}
      </div>

      <div role="tabpanel" className="min-h-0 overflow-y-auto pr-1">
        {tab === "timeline" ? (
          <TimelinePanel t={t} lang={lang} profile={props.profile} />
        ) : tab === "history" ? (
          history.length === 0 ? (
            <p className="px-2.5 text-sm text-ink-3">{t.historyEmpty}</p>
          ) : (
            <div className="flex flex-col gap-3">
              {groupByDay(history, t).map((group) => (
                <section key={group.label}>
                  <h3 className="px-2.5 pb-1 text-xs font-medium text-ink-3">{group.label}</h3>
                  <ul className="flex flex-col gap-0.5">
                    {group.items.map((h) => {
                      const current = props.currentId === h.id;
                      return (
                        <li key={h.id}>
                          <button
                            type="button"
                            onClick={() => props.onOpen(h.id)}
                            aria-current={current}
                            className={`w-full rounded-lg px-2.5 py-2 text-left text-sm transition-colors ${
                              current ? "bg-panel text-ink shadow-[0_1px_2px_var(--shadow)]" : "text-ink-2 hover:bg-panel hover:text-ink"
                            }`}
                          >
                            <span className="line-clamp-2">{h.question}</span>
                            <span className="mt-0.5 block text-xs text-ink-3 tabular-nums">
                              {(group.recent ? timeFmt : fullFmt).format(new Date(h.created_at))}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ))}
            </div>
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
