"use client";

import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  deleteAccount,
  loadDashboard,
  loadMyChanges,
  loadMyObligations,
  loadMyQuestions,
  loadTimeline,
} from "@/lib/api";
import { ACTIVITIES, APPLIES, CUSTOMERS, FIRM_TYPES, REGIMES, SIZES, TOOL_NAMES, type Strings } from "@/lib/i18n";
import { toCsv } from "@/lib/csv";
import { readStored, writeStored } from "@/lib/storage";
import { PERIODS, type BlindSpot, type CitedProvision, type DashboardData, type InventoryRow, type Lang, type Period, type QuestionFilter, type QuestionRow, type SourceChange, type TimelineEntry, type User } from "@/lib/types";
import { ActivityChart, TopicBars } from "./Charts";
import { KeysSection } from "./KeysSection";
import { OperatorSection } from "./OperatorSection";
import { LayerGlyph } from "./LayerGlyph";

type Section = "overview" | "questions" | "obligations" | "dates" | "account" | "operator";
const SECTIONS: Section[] = ["overview", "questions", "obligations", "dates", "account"];
const ALL_SECTIONS: Section[] = [...SECTIONS, "operator"];

export function Dashboard(props: {
  t: Strings;
  lang: Lang;
  user: User | null;
  refreshKey: number;
  onSignIn: () => void;
  onSignUp: () => void;
  onSignOut: () => void;
  onEditProfile: () => void;
  onOpenAnswer: (id: string) => void;
  onNewQuestion: () => void;
  onAsk: (question: string) => void;
  onDeleted: () => void;
}) {
  const { t, lang, user } = props;
  const [section, setSection] = useState<Section>(() => {
    const hash = window.location.hash.slice(1) as Section;
    return (props.user?.operator ? ALL_SECTIONS : SECTIONS).includes(hash) ? hash : "overview";
  });
  const [period, setPeriod] = useState<Period>(() => {
    const stored = readStored<Period>("period", 30);
    return PERIODS.includes(stored) ? stored : 30;
  });
  const [filter, setFilter] = useState<QuestionFilter>({});
  const [data, setData] = useState<DashboardData | null>(null);
  const [changes, setChanges] = useState<SourceChange[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!props.user) return; // a guest has no answers of their own
    loadMyChanges().then(setChanges).catch(() => undefined);
  }, [props.user, props.refreshKey]);
  const locale = lang === "de" ? "de-DE" : "en-GB";
  const dateFmt = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric" });
  const timeFmt = new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

  const show = (next: Section) => {
    setSection(next);
    window.history.replaceState(null, "", `/dashboard#${next}`);
  };

  /** Click-through: the questions behind a bar, a Regime or a Provision. */
  const openQuestions = (next: QuestionFilter) => {
    setFilter(next);
    show("questions");
  };

  const choosePeriod = (next: Period) => {
    setPeriod(next);
    writeStored("period", next);
  };

  useEffect(() => {
    if (!user) return;
    let current = true;
    loadDashboard(period)
      .then((d) => {
        if (current) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: ApiError) => current && setError(e.message));
    return () => {
      current = false;
    };
  }, [user, props.refreshKey, period]);

  if (!user) {
    return (
      <section aria-labelledby="guest-dashboard-title" className="mx-auto mt-6 max-w-[62ch] rounded-2xl border border-line bg-panel px-6 py-6 shadow-raise">
        <p className="text-xs font-semibold uppercase tracking-wide text-accent">{t.guestDashboardFlag}</p>
        <h1 id="guest-dashboard-title" className="mt-2 text-[26px] font-semibold leading-tight tracking-tight">
          {t.guestDashboardTitle}
        </h1>
        <p className="mt-3 text-ink-2">{t.guestDashboard}</p>
        <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-ink-2">
          {t.guestDashboardPoints.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button type="button" onClick={props.onSignUp} className="btn btn-primary">
            {t.signUp}
          </button>
          <button type="button" onClick={props.onSignIn} className="btn btn-outline">
            {t.signIn}
          </button>
        </div>
        <p className="mt-4 text-xs text-ink-3">{t.guestDashboardFree}</p>
      </section>
    );
  }

  const labels: Record<Section, string> = {
    overview: t.navOverview,
    questions: t.navQuestions,
    obligations: t.navObligations,
    dates: t.navDates,
    account: t.navAccount,
    operator: t.navOperator,
  };
  const sections = user.operator ? ALL_SECTIONS : SECTIONS;
  const topics = (regimes: string[]) => regimes.map((r) => REGIMES[r]?.[lang] ?? r);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[200px_minmax(0,1fr)]">
      <nav aria-label={t.dashboard} className="min-w-0 lg:sticky lg:top-4 lg:self-start">
        <ul className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
          {sections.map((s) => (
            <li key={s}>
              <button
                type="button"
                onClick={() => {
                  if (s === "questions") setFilter({});
                  show(s);
                }}
                aria-current={section === s ? "page" : undefined}
                className={`w-full whitespace-nowrap rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  section === s ? "bg-panel font-medium text-ink shadow-[0_1px_2px_var(--shadow)]" : "text-ink-2 hover:bg-panel hover:text-ink"
                }`}
              >
                {labels[s]}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <div className="min-w-0">
        {error && <p role="alert" className="mb-4 text-sm text-red">{error}</p>}

        {section === "overview" && (
          <div className="flex flex-col gap-6">
            <header className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h1 className="text-[26px] font-semibold leading-tight tracking-tight">{t.greeting(user.name)}</h1>
                {user.profile && (
                  <p className="mt-1 text-sm text-ink-2">
                    {FIRM_TYPES[user.profile.firm_type]?.[lang]}, {SIZES[user.profile.size]?.[lang]}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <div role="group" aria-label={t.period} className="switch text-sm">
                  {PERIODS.map((d) => (
                    <button key={d} type="button" aria-pressed={period === d} onClick={() => choosePeriod(d)}>
                      {t.periodShort(d)}
                    </button>
                  ))}
                </div>
                <button type="button" onClick={props.onNewQuestion} className="btn btn-primary">
                  {t.newQuestionCta}
                </button>
              </div>
            </header>

            <dl className="grid grid-cols-[minmax(0,1fr)] gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-line bg-panel px-5 py-4">
                <dt className="text-sm text-ink-2">{t.statQuestions}</dt>
                <dd className="mt-1 text-2xl font-semibold tabular-nums">{data?.stats.questions ?? "–"}</dd>
                <dd className="text-xs text-ink-3">
                  {data && period !== 0 ? t.statOfTotal(data.stats.questions_total) : ""}
                  {data?.stats.refused ? ` · ${t.statRefused(data.stats.refused)}` : ""}
                </dd>
              </div>
              <div className="rounded-xl border border-line bg-panel px-5 py-4">
                <dt className="text-sm text-ink-2">{t.statObligations}</dt>
                <dd className="mt-1 text-2xl font-semibold tabular-nums">{data?.stats.obligations ?? "–"}</dd>
              </div>
              <div className="rounded-xl border border-line bg-panel px-5 py-4">
                <dt className="text-sm text-ink-2">{t.nextDate}</dt>
                {data?.upcoming[0] ? (
                  <>
                    <dd className="mt-1 text-2xl font-semibold tabular-nums">{dateFmt.format(new Date(data.upcoming[0].date))}</dd>
                    <dd className="truncate text-xs text-ink-3" title={data.upcoming[0].what}>
                      {data.upcoming[0].source}: {data.upcoming[0].what}
                    </dd>
                  </>
                ) : (
                  <dd className="mt-1 text-sm text-ink-3">{t.noNextDate}</dd>
                )}
              </div>
            </dl>

            {changes.length > 0 && (
              <section aria-labelledby="changes-title" className="rounded-xl border border-amber/40 bg-amber-soft px-5 py-4">
                <h2 id="changes-title" className="text-sm font-semibold">{t.yourChangesTitle}</h2>
                <p className="mt-1 text-sm text-ink-2">{t.yourChangesIntro}</p>
                <ul className="mt-2 flex flex-col gap-1 text-sm">
                  {changes.map((c) => (
                    <li key={c.source_id} className="flex flex-wrap items-baseline gap-x-3">
                      <span className="font-medium">{c.short_title}</span>
                      {c.at && <span className="text-ink-3 tabular-nums">{dateFmt.format(new Date(c.at))}</span>}
                      <span className="text-ink-2">{t.changeCounts(c.added, c.removed, c.changed)}</span>
                      <span className="text-ink-3">{t.yourChangesAnswers(c.answers ?? 0)}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <section aria-labelledby="activity-title" className="rounded-xl border border-line bg-panel px-5 py-4">
                <h2 id="activity-title" className="text-sm font-semibold">{t.activityTitle}</h2>
                <p className="mb-3 text-xs text-ink-3">{t.periodLong(period)}</p>
                {data && (
                  <ActivityChart
                    data={data.activity}
                    lang={lang}
                    tooltip={t.activityTooltip}
                    label={t.activityTitle}
                    onSelect={(day) => openQuestions({ day })}
                  />
                )}
              </section>
              <section aria-labelledby="topics-title" className="rounded-xl border border-line bg-panel px-5 py-4">
                <h2 id="topics-title" className="text-sm font-semibold">{t.regimesTitle}</h2>
                <p className="mb-2 text-xs text-ink-3">
                  {t.regimesSub} ({t.periodLong(period)})
                </p>
                {data && (
                  <TopicBars
                    rows={data.regimes.map((r) => ({ id: r.regime, label: REGIMES[r.regime]?.[lang] ?? r.regime, count: r.count }))}
                    empty={t.regimesEmpty}
                    onSelect={(regime) => openQuestions({ regime, days: period })}
                    selectLabel={t.showQuestions}
                  />
                )}
              </section>
            </div>
            <p className="-mt-3 text-xs text-ink-3">{t.chartHint}</p>

            <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-2">
              <section aria-labelledby="provisions-title" className="rounded-xl border border-line bg-panel px-5 py-4">
                <h2 id="provisions-title" className="text-sm font-semibold">{t.topProvisionsTitle}</h2>
                <p className="mb-2 text-xs text-ink-3">
                  {t.topProvisionsSub} ({t.periodLong(period)})
                </p>
                {data && <TopProvisions rows={data.provisions} t={t} lang={lang} onSelect={(provision) => openQuestions({ provision, days: period })} />}
              </section>
              <section aria-labelledby="blind-title" className="rounded-xl border border-line bg-panel px-5 py-4">
                <h2 id="blind-title" className="text-sm font-semibold">{t.blindTitle}</h2>
                <p className="mb-3 text-xs text-ink-3">{t.blindSub}</p>
                {data && <BlindSpots spots={data.blind_spots} t={t} lang={lang} onAsk={props.onAsk} onEditProfile={props.onEditProfile} />}
              </section>
            </div>

            <section aria-labelledby="recent-title">
              <div className="mb-2 flex items-center justify-between">
                <h2 id="recent-title" className="text-sm font-semibold">{t.recentTitle}</h2>
                <button type="button" onClick={() => show("questions")} className="btn btn-quiet btn-sm">
                  {t.showAll}
                </button>
              </div>
              <QuestionTable rows={data?.recent ?? []} t={t} lang={lang} timeFmt={timeFmt} topics={topics} onOpen={props.onOpenAnswer} />
            </section>
          </div>
        )}

        {section === "questions" && (
          <QuestionsSection
            t={t}
            lang={lang}
            timeFmt={timeFmt}
            dateFmt={dateFmt}
            topics={topics}
            filter={filter}
            onFilter={setFilter}
            onOpen={props.onOpenAnswer}
            refreshKey={props.refreshKey}
          />
        )}

        {section === "obligations" && <ObligationsSection t={t} timeFmt={timeFmt} onOpen={props.onOpenAnswer} refreshKey={props.refreshKey} />}

        {section === "dates" && <DatesSection t={t} lang={lang} user={user} dateFmt={dateFmt} />}

        {section === "operator" && user.operator && (
          <OperatorSection t={t} lang={lang} period={period} onPeriod={choosePeriod} dateFmt={dateFmt} timeFmt={timeFmt} />
        )}

        {section === "account" && (
          <div className="flex max-w-[640px] flex-col gap-6">
            <h1 className="text-[26px] font-semibold leading-tight tracking-tight">{t.accountTitle}</h1>
            <section aria-labelledby="acc-profile" className="rounded-xl border border-line bg-panel px-5 py-4">
              <div className="flex items-center justify-between gap-3">
                <h2 id="acc-profile" className="text-sm font-semibold">{t.profile}</h2>
                <button type="button" onClick={props.onEditProfile} className="btn btn-outline btn-sm">
                  {user.profile ? t.editProfile : t.editProfileCta}
                </button>
              </div>
              {user.profile ? (
                <div className="mt-2 text-sm">
                  <p className="font-medium">
                    {FIRM_TYPES[user.profile.firm_type]?.[lang]}, {SIZES[user.profile.size]?.[lang]}, {CUSTOMERS[user.profile.customers]?.[lang]}
                  </p>
                  <p className="mt-1 text-ink-2">{user.profile.activities.map((a) => ACTIVITIES[a]?.[lang] ?? a).join(", ") || "–"}</p>
                </div>
              ) : (
                <p className="mt-2 text-sm text-ink-3">{t.noProfile}</p>
              )}
            </section>
            <KeysSection t={t} timeFmt={timeFmt} />
            <section aria-labelledby="acc-account" className="rounded-xl border border-line bg-panel px-5 py-4 text-sm">
              <h2 id="acc-account" className="font-semibold">{t.account}</h2>
              <p className="mt-2">
                <span className="text-ink-2">{t.signedInAs} </span>
                {user.name ? `${user.name}, ` : ""}
                {user.email}
              </p>
              <p className="mt-2 text-xs text-ink-3">{t.accountPrivacy}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button type="button" onClick={props.onSignOut} className="btn btn-outline">
                  {t.signOut}
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    if (!window.confirm(t.deleteConfirm)) return;
                    try {
                      await deleteAccount();
                      props.onDeleted();
                    } catch (e) {
                      setError((e as ApiError).message);
                    }
                  }}
                  className="btn text-red hover:bg-red-soft"
                >
                  {t.deleteAccount}
                </button>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

function QuestionTable(props: {
  rows: QuestionRow[];
  t: Strings;
  lang: Lang;
  timeFmt: Intl.DateTimeFormat;
  topics: (r: string[]) => string[];
  onOpen: (id: string) => void;
  empty?: string;
}) {
  const { t, lang } = props;
  if (props.rows.length === 0) return <p className="rounded-xl border border-line bg-panel px-5 py-4 text-sm text-ink-3">{props.empty ?? t.archiveEmpty}</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-panel">
      <table className="w-full border-collapse text-sm md:min-w-[720px]">
        <thead>
          <tr className="border-b border-line text-left text-xs text-ink-2">
            <th scope="col" className="w-[6.5rem] px-3 py-2 font-medium sm:w-[9.5rem] sm:px-4">{t.colDate}</th>
            <th scope="col" className="px-4 py-2 font-medium">{t.colQuestion}</th>
            <th scope="col" className="w-[11rem] px-4 py-2 font-medium">{t.colTopics}</th>
            <th scope="col" className="hidden w-[12rem] px-4 py-2 font-medium md:table-cell">{t.colChecks}</th>
            <th scope="col" className="hidden w-[5.5rem] px-4 py-2 text-right font-medium md:table-cell">{t.colObligations}</th>
          </tr>
        </thead>
        <tbody>
          {props.rows.map((r) => (
            <tr key={r.id} onClick={() => props.onOpen(r.id)} className="cursor-pointer border-t border-line align-top first:border-t-0 hover:bg-panel-2">
              <td className="px-3 py-2.5 text-xs text-ink-2 tabular-nums sm:px-4 sm:text-sm">{props.timeFmt.format(new Date(r.created_at))}</td>
              <td className="px-4 py-2.5">
                <button type="button" onClick={(e) => { e.stopPropagation(); props.onOpen(r.id); }} className="text-left hover:text-accent">
                  {r.question}
                  {r.refused && <span className="ml-2 rounded-full bg-track px-1.5 py-px text-[11px] text-ink-3">{props.t.refusedMark}</span>}
                </button>
              </td>
              <td className="px-4 py-2.5">
                <span className="flex flex-wrap gap-1">
                  {props.topics(r.regimes).map((name) => (
                    <span key={name} className="rounded-full bg-track px-2 py-0.5 text-xs text-ink-2">{name}</span>
                  ))}
                </span>
              </td>
              <td className="hidden px-4 py-2.5 text-xs text-ink-2 md:table-cell">{r.tools.map((n) => TOOL_NAMES[n]?.[lang] ?? n).join(", ") || "–"}</td>
              <td className="hidden px-4 py-2.5 text-right tabular-nums md:table-cell">{r.obligation_count || "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function QuestionsSection(props: {
  t: Strings;
  lang: Lang;
  timeFmt: Intl.DateTimeFormat;
  dateFmt: Intl.DateTimeFormat;
  topics: (r: string[]) => string[];
  filter: QuestionFilter;
  onFilter: (f: QuestionFilter) => void;
  onOpen: (id: string) => void;
  refreshKey: number;
}) {
  const { t, lang, filter } = props;
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<QuestionRow[] | null>(null);
  const filterKey = JSON.stringify(filter);
  useEffect(() => {
    let current = true;
    const timer = setTimeout(() => {
      loadMyQuestions(search, JSON.parse(filterKey) as QuestionFilter)
        .then((list) => current && setRows(list))
        .catch(() => current && setRows([]));
    }, 250);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [search, filterKey, props.refreshKey]);
  const chips: { key: keyof QuestionFilter; label: string }[] = [];
  if (filter.regime) chips.push({ key: "regime", label: `${t.filterRegime}: ${REGIMES[filter.regime]?.[lang] ?? filter.regime}` });
  if (filter.provision) chips.push({ key: "provision", label: `${t.filterProvision}: ${filter.provision}` });
  if (filter.day) chips.push({ key: "day", label: `${t.filterDay}: ${props.dateFmt.format(new Date(filter.day))}` });
  if (filter.days) chips.push({ key: "days", label: `${t.period}: ${t.periodLong(filter.days)}` });
  const remove = (key: keyof QuestionFilter) => {
    const next = { ...filter };
    delete next[key];
    props.onFilter(next);
  };
  return (
    <section aria-labelledby="questions-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 id="questions-title" className="text-[26px] font-semibold leading-tight tracking-tight">{t.archive}</h1>
        <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t.archiveSearch} aria-label={t.archiveSearch}
          className="field w-full sm:w-72" />
      </div>
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {chips.map((c) => (
            <span key={c.key} className="chip gap-1 py-0.5 pr-1 text-[13px]">
              {c.label}
              <button
                type="button"
                onClick={() => remove(c.key)}
                aria-label={t.removeFilter(c.label)}
                className="grid h-6 w-6 place-items-center rounded-full text-ink-3 hover:bg-track hover:text-ink"
              >
                <svg aria-hidden width="10" height="10" viewBox="0 0 10 10">
                  <path d="M2 2l6 6M8 2 2 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </span>
          ))}
          {chips.length > 1 && (
            <button type="button" onClick={() => props.onFilter({})} className="btn btn-quiet btn-sm">
              {t.clearFilters}
            </button>
          )}
        </div>
      )}
      {rows && (
        <QuestionTable rows={rows} t={t} lang={props.lang} timeFmt={props.timeFmt} topics={props.topics} onOpen={props.onOpen}
          empty={search || chips.length ? t.archiveNoMatch : t.archiveEmpty} />
      )}
    </section>
  );
}

function ObligationsSection(props: { t: Strings; timeFmt: Intl.DateTimeFormat; onOpen: (id: string) => void; refreshKey: number }) {
  const { t } = props;
  const [rows, setRows] = useState<InventoryRow[] | null>(null);
  const [search, setSearch] = useState("");
  useEffect(() => {
    let current = true;
    loadMyObligations()
      .then((list) => current && setRows(list))
      .catch(() => current && setRows([]));
    return () => {
      current = false;
    };
  }, [props.refreshKey]);
  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (rows ?? []).filter((r) => !q || [r.addressee, r.action, r.deadline, r.provision, r.question].join(" ").toLowerCase().includes(q));
  }, [rows, search]);
  const download = () => {
    const header = [...t.obligationColumns, t.colFrom];
    const blob = new Blob([toCsv(header, shown.map((r) => [r.addressee, r.action, r.deadline, r.provision, r.link, r.question]))], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "pflichten.csv";
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <section aria-labelledby="inventory-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 id="inventory-title" className="text-[26px] font-semibold leading-tight tracking-tight">{t.inventoryTitle}</h1>
          <p className="mt-1 max-w-[70ch] text-sm text-ink-2">{t.inventoryIntro}</p>
        </div>
        <div className="flex w-full flex-wrap items-center gap-3 sm:w-auto">
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t.inventorySearch} aria-label={t.inventorySearch}
            className="field w-full sm:w-64" />
          {shown.length > 0 && (
            <button type="button" onClick={download} className="btn btn-outline">{t.downloadAll}</button>
          )}
        </div>
      </div>
      {rows && shown.length === 0 ? (
        <p className="rounded-xl border border-line bg-panel px-5 py-4 text-sm text-ink-3">{search ? t.archiveNoMatch : t.inventoryEmpty}</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line bg-panel">
          <table className="w-full min-w-[820px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-ink-2">
                {[t.obligationColumns[0], t.obligationColumns[1], t.obligationColumns[2], t.obligationColumns[3], t.colFrom].map((h) => (
                  <th key={h} scope="col" className="px-4 py-2 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r, i) => (
                <tr key={i} className="border-t border-line align-top first:border-t-0">
                  <td className="px-4 py-2.5">{r.addressee}</td>
                  <td className="px-4 py-2.5">{r.action}</td>
                  <td className="px-4 py-2.5 text-ink-2">{r.deadline || "–"}</td>
                  <td className="px-4 py-2.5">
                    <a href={r.link} target="_blank" rel="noreferrer" className="provision whitespace-nowrap text-accent underline underline-offset-2">{r.provision}</a>
                  </td>
                  <td className="px-4 py-2.5">
                    <button type="button" onClick={() => props.onOpen(r.answer_id)} className="text-left text-xs text-ink-2 hover:text-accent">
                      {r.question}
                      <span className="block text-ink-3 tabular-nums">{props.timeFmt.format(new Date(r.created_at))}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function DatesSection(props: { t: Strings; lang: Lang; user: User; dateFmt: Intl.DateTimeFormat }) {
  const { t, lang, user } = props;
  const [entries, setEntries] = useState<TimelineEntry[] | null>(null);
  useEffect(() => {
    let current = true;
    loadTimeline(user.profile, true)
      .then((list) => current && setEntries(list))
      .catch(() => current && setEntries([]));
    return () => {
      current = false;
    };
  }, [user.profile]);
  return (
    <section aria-labelledby="dates-title" className="flex max-w-[860px] flex-col gap-3">
      <div>
        <h1 id="dates-title" className="text-[26px] font-semibold leading-tight tracking-tight">{t.datesTitle}</h1>
        <p className="mt-1 text-sm text-ink-2">{user.profile ? t.datesIntro : t.datesIntroAll}</p>
      </div>
      <ol className="rounded-xl border border-line bg-panel">
        {(entries ?? []).map((e, i) => (
          <li key={i} className="grid grid-cols-[8.5rem_1fr] gap-4 border-t border-line px-4 py-3 first:border-t-0 sm:grid-cols-[10rem_1fr]">
            <div>
              <time dateTime={e.date} className="block font-semibold tabular-nums">{props.dateFmt.format(new Date(e.date))}</time>
              <span className="text-xs text-ink-3">{t.inDays(e.days_from_today)}</span>
            </div>
            <div className="text-sm">
              <a href={e.link} target="_blank" rel="noreferrer" className="provision hover:text-accent">{e.source}</a>{" "}
              <span className="text-xs text-ink-3">{REGIMES[e.regime]?.[lang]}</span>
              <span className="block text-ink-2">{e.what}</span>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Provisions cited in the most answers; a row opens those answers, the link the official text. */
function TopProvisions(props: { rows: CitedProvision[]; t: Strings; lang: Lang; onSelect: (provision: string) => void }) {
  const { rows, t, lang } = props;
  if (rows.length === 0) return <p className="text-sm text-ink-3">{t.topProvisionsEmpty}</p>;
  const max = rows[0].count;
  return (
    <ol className="flex flex-col gap-0.5">
      {rows.map((p) => (
        <li key={p.provision} className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => props.onSelect(p.provision)}
            aria-label={`${t.showQuestions(p.provision)}: ${p.count}`}
            className="grid min-w-0 flex-1 grid-cols-[minmax(0,1fr)_4rem] items-center gap-3 rounded-lg px-2 py-1.5 text-left text-sm transition-colors hover:bg-panel-2 sm:grid-cols-[minmax(0,1fr)_6rem]"
          >
            <span className="flex min-w-0 items-start gap-2">
              {p.layer && (
                <span className="mt-0.5">
                  <LayerGlyph layer={p.layer} lang={lang} size={14} />
                </span>
              )}
              <span className="min-w-0">
                <span className="provision">{p.provision}</span>
                {p.title && <span className="block truncate text-xs text-ink-2">{p.title}</span>}
              </span>
            </span>
            <span className="flex items-center gap-2">
              <span className="block h-3 rounded-r-[4px] bg-chart" style={{ width: `calc((100% - 1.75rem) * ${p.count / max})` }} />
              <span className="tabular-nums">{p.count}</span>
            </span>
          </button>
          {p.link && (
            <a href={p.link} target="_blank" rel="noreferrer" className="btn btn-quiet btn-sm shrink-0" aria-label={`${t.openText}: ${p.provision}`} title={t.openText}>
              <svg aria-hidden width="12" height="12" viewBox="0 0 12 12" className="sm:hidden">
                <path d="M5 2H2.5v7.5H10V7M7 2h3v3M10 2 5.5 6.5" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="hidden sm:inline">{t.openText}</span>
            </a>
          )}
        </li>
      ))}
    </ol>
  );
}

/** Sources that apply to the Firm Profile but never came up, each with a ready question. */
function BlindSpots(props: {
  spots: BlindSpot[] | null;
  t: Strings;
  lang: Lang;
  onAsk: (question: string) => void;
  onEditProfile: () => void;
}) {
  const { spots, t, lang } = props;
  if (spots === null) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-ink-2">{t.blindNoProfile}</p>
        <button type="button" onClick={props.onEditProfile} className="btn btn-outline btn-sm">
          {t.editProfileCta}
        </button>
      </div>
    );
  }
  const open = spots.filter((s) => s.questions === 0);
  const covered = spots.filter((s) => s.questions > 0);
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm">{open.length ? t.blindSummary(open.length, spots.length) : t.blindNone}</p>
      {open.length > 0 && (
        <ul className="divide-y divide-line rounded-lg border border-line">
          {open.map((s) => (
            <li key={s.short_title} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2">
              <LayerGlyph layer={s.layer} lang={lang} size={14} />
              <span className="min-w-0 flex-1">
                <a href={s.url} target="_blank" rel="noreferrer" className="provision hover:text-accent">
                  {s.short_title}
                </a>
                <span className="block text-xs text-ink-3">{REGIMES[s.regime]?.[lang] ?? s.regime}</span>
              </span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${s.applies === "yes" ? "bg-amber-soft text-amber" : "bg-track text-ink-2"}`}>
                {APPLIES[s.applies]?.[lang] ?? s.applies}
              </span>
              <button type="button" onClick={() => props.onAsk(t.blindQuestion(s.short_title))} className="btn btn-accent btn-sm">
                {t.blindAsk}
              </button>
            </li>
          ))}
        </ul>
      )}
      {covered.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-medium text-ink-3">{t.blindCovered}</p>
          <ul className="flex flex-wrap gap-1.5">
            {covered.map((s) => (
              <li key={s.short_title} className="rounded-full bg-track px-2.5 py-0.5 text-xs text-ink-2">
                <span className="provision text-ink">{s.short_title}</span> <span className="tabular-nums">{s.questions}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
