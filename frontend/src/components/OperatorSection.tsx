"use client";

import { useEffect, useState } from "react";

import { ApiError, loadOperatorOverview, loadUpdateRuns, startUpdateRun } from "@/lib/api";
import type { Strings } from "@/lib/i18n";
import { PERIODS, type Lang, type OperatorData, type Period, type UpdateRuns } from "@/lib/types";
import { ActivityChart, TopicBars } from "./Charts";

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border border-line bg-panel px-5 py-4">
      <dt className="text-sm text-ink-2">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd>
      {note && <dd className="text-xs text-ink-3">{note}</dd>}
    </div>
  );
}

/** The Operator's page (ADR 0006): figures across all accounts, never question texts. */
export function OperatorSection(props: {
  t: Strings;
  lang: Lang;
  period: Period;
  onPeriod: (p: Period) => void;
  dateFmt: Intl.DateTimeFormat;
  timeFmt: Intl.DateTimeFormat;
}) {
  const { t, lang, period } = props;
  const [data, setData] = useState<OperatorData | null>(null);
  const [updates, setUpdates] = useState<UpdateRuns | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadUpdates = () =>
    loadUpdateRuns()
      .then((u) => {
        setUpdates(u);
        setError(null);
      })
      .catch((e: ApiError) => setError(e.message));
  useEffect(() => {
    loadOperatorOverview(period)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: ApiError) => setError(e.message));
  }, [period]);
  useEffect(() => {
    loadUpdates();
  }, []);
  useEffect(() => {
    if (!updates?.running) return;
    const timer = setInterval(loadUpdates, 5000);
    return () => clearInterval(timer);
  }, [updates?.running]);
  const pct = (v: number | null) => (v == null ? "–" : `${Math.round(v * 100)} %`);
  const s = data?.stats;
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-semibold leading-tight tracking-tight">{t.operatorTitle}</h1>
          <p className="mt-1 text-sm text-ink-2">{t.operatorIntro}</p>
        </div>
        <div role="group" aria-label={t.period} className="switch text-sm">
          {PERIODS.map((d) => (
            <button key={d} type="button" aria-pressed={period === d} onClick={() => props.onPeriod(d)}>
              {t.periodShort(d)}
            </button>
          ))}
        </div>
      </header>
      {error && <p role="alert" className="text-sm text-red">{error}</p>}
      <dl className="grid grid-cols-[minmax(0,1fr)] gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label={t.opQuestions} value={s ? String(s.questions) : "–"} note={s ? t.opAnswered(s.answered, s.refused) : undefined} />
        <Tile label={t.opAccounts} value={s ? String(s.accounts) : "–"} note={s ? `${t.opGuests(s.guest_questions)} · ${t.opKeys(s.via_api_key)}` : undefined} />
        <Tile label={t.opCost} value={s ? t.cost(s.cost_usd.toFixed(3)) : "–"} />
        <Tile label={t.opErrors} value={s ? String(s.errors) : "–"} />
        <Tile label={t.opSeconds} value={s?.avg_seconds != null ? t.traceSeconds(s.avg_seconds) : "–"} />
        <Tile label={t.opTopScore} value={s?.avg_top_score != null ? s.avg_top_score.toFixed(3) : "–"} />
        <Tile label={t.opCited} value={pct(s?.cited_share ?? null)} />
        <Tile label={t.opCoverage} value={pct(s?.coverage_full_share ?? null)} />
      </dl>
      <section className="rounded-xl border border-line bg-panel px-5 py-4">
        <h2 className="text-sm font-semibold">{t.activityTitle}</h2>
        <div className="mt-3">
          {data && <ActivityChart data={data.activity} lang={lang} tooltip={t.activityTooltip} label={t.activityTitle} />}
        </div>
      </section>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-2">
        <section className="rounded-xl border border-line bg-panel px-5 py-4">
          <h2 className="text-sm font-semibold">{t.opModels}</h2>
          <div className="mt-3">
            <TopicBars rows={(data?.models ?? []).map((m) => ({ id: m.id, label: `${m.id.split("/").pop()} · ${t.cost(m.cost_usd.toFixed(3))}`, count: m.questions }))} empty={t.regimesEmpty} />
          </div>
        </section>
        <section className="rounded-xl border border-line bg-panel px-5 py-4">
          <h2 className="text-sm font-semibold">{t.opStrategies}</h2>
          <div className="mt-3">
            <TopicBars rows={(data?.strategies ?? []).map((m) => ({ id: m.id, label: `${t.strategies[m.id as "vector" | "hybrid"] ?? m.id} · ${t.cost(m.cost_usd.toFixed(3))}`, count: m.questions }))} empty={t.regimesEmpty} />
          </div>
        </section>
        <section className="rounded-xl border border-line bg-panel px-5 py-4">
          <h2 className="text-sm font-semibold">{t.opRefusals}</h2>
          <div className="mt-3">
            <TopicBars rows={(data?.refusals ?? []).map((r) => ({ id: r.reason, label: r.reason, count: r.count }))} empty={t.regimesEmpty} />
          </div>
        </section>
        <section className="rounded-xl border border-line bg-panel px-5 py-4">
          <h2 className="text-sm font-semibold">{t.opErrorKinds}</h2>
          <div className="mt-3">
            <TopicBars rows={(data?.errors ?? []).map((e) => ({ id: e.status, label: `HTTP ${e.status}`, count: e.count }))} empty={t.regimesEmpty} />
          </div>
        </section>
      </div>
      <section className="rounded-xl border border-line bg-panel px-5 py-4 text-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">{t.opUpdates}</h2>
          <button
            type="button"
            disabled={!updates || updates.running}
            onClick={async () => {
              try {
                await startUpdateRun();
                setTimeout(loadUpdates, 500);
              } catch (e) {
                setError((e as ApiError).message);
              }
            }}
            className="btn btn-primary btn-sm"
          >
            {t.opCheckNow}
          </button>
        </div>
        {updates && <p className="mt-2 text-ink-2">{t.opUpdatesIntro(updates.scheduled, updates.hour)}</p>}
        {updates?.running && <p className="mt-2 animate-pulse text-accent">{t.opRunning}</p>}
        {updates && updates.runs.length === 0 && <p className="mt-3 text-ink-3">{t.opNoRuns}</p>}
        {updates && updates.runs.length > 0 && (
          <ul className="mt-3 divide-y divide-line">
            {updates.runs.map((r) => (
              <li key={r.id} className="flex flex-wrap items-baseline gap-x-3 py-1.5">
                <span className="tabular-nums">{props.timeFmt.format(new Date(r.started_at))}</span>
                <span className="text-ink-3">{r.trigger === "manual" ? t.triggerManual : t.triggerScheduled}</span>
                <span className="text-ink-2">{r.finished_at ? t.opRunRow(r.checked, r.changed, r.failed) : t.opRunning}</span>
                {r.notes.length > 0 && <span className="text-xs text-red">{r.notes.map((n) => `${n.source_id}: ${n.error}`).join("; ")}</span>}
              </li>
            ))}
          </ul>
        )}
        <h3 className="mt-5 font-semibold">{t.opChanges}</h3>
        {updates && updates.changes.length === 0 && <p className="mt-2 text-ink-3">{t.opNoChanges}</p>}
        {updates && updates.changes.length > 0 && (
          <ul className="mt-2 divide-y divide-line">
            {updates.changes.map((c) => (
              <li key={c.id} className="flex flex-wrap items-baseline gap-x-3 py-1.5">
                <span className="tabular-nums">{c.at && props.dateFmt.format(new Date(c.at))}</span>
                <span className="font-medium">{c.short_title}</span>
                <span className="text-ink-2">{t.changeCounts(c.added, c.removed, c.changed)}</span>
                <span className="text-xs text-ink-3 tabular-nums">{c.passages_before} → {c.passages_after}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
