"use client";

import { useEffect, useMemo, useState } from "react";

import { ApiError, deleteAccount, loadDashboard, loadMyObligations, loadMyQuestions, loadTimeline } from "@/lib/api";
import { ACTIVITIES, CUSTOMERS, FIRM_TYPES, REGIMES, SIZES, TOOL_NAMES, type Strings } from "@/lib/i18n";
import type { DashboardData, InventoryRow, Lang, QuestionRow, TimelineEntry, User } from "@/lib/types";
import { ActivityChart, TopicBars } from "./Charts";

type Section = "overview" | "questions" | "obligations" | "dates" | "account";
const SECTIONS: Section[] = ["overview", "questions", "obligations", "dates", "account"];

function csv(rows: InventoryRow[], header: string[]): string {
  const cell = (v: string) => `"${(v ?? "").replace(/"/g, '""')}"`;
  return (
    "﻿" +
    [header.map(cell).join(";")]
      .concat(rows.map((r) => [r.addressee, r.action, r.deadline, r.provision, r.link, r.question].map(cell).join(";")))
      .join("\r\n")
  );
}

export function Dashboard(props: {
  t: Strings;
  lang: Lang;
  user: User | null;
  refreshKey: number;
  onSignIn: () => void;
  onSignOut: () => void;
  onEditProfile: () => void;
  onOpenAnswer: (id: string) => void;
  onNewQuestion: () => void;
  onDeleted: () => void;
}) {
  const { t, lang, user } = props;
  const [section, setSection] = useState<Section>(() => {
    const hash = window.location.hash.slice(1) as Section;
    return SECTIONS.includes(hash) ? hash : "overview";
  });
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const locale = lang === "de" ? "de-DE" : "en-GB";
  const dateFmt = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric" });
  const timeFmt = new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

  const show = (next: Section) => {
    setSection(next);
    window.history.replaceState(null, "", `/dashboard#${next}`);
  };

  useEffect(() => {
    if (!user) return;
    let current = true;
    loadDashboard()
      .then((d) => current && setData(d))
      .catch((e: ApiError) => current && setError(e.message));
    return () => {
      current = false;
    };
  }, [user, props.refreshKey]);

  if (!user) {
    return (
      <section className="max-w-[60ch] py-6">
        <h1 className="text-xl font-semibold">{t.dashboard}</h1>
        <p className="mt-2 text-ink-2">{t.guestDashboard}</p>
        <button type="button" onClick={props.onSignIn} className="mt-4 rounded bg-accent px-4 py-2 text-sm font-medium text-accent-ink">
          {t.signIn} / {t.signUp}
        </button>
      </section>
    );
  }

  const labels: Record<Section, string> = {
    overview: t.navOverview,
    questions: t.navQuestions,
    obligations: t.navObligations,
    dates: t.navDates,
    account: t.navAccount,
  };
  const topics = (regimes: string[]) => regimes.map((r) => REGIMES[r]?.[lang] ?? r);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[200px_minmax(0,1fr)]">
      <nav aria-label={t.dashboard} className="min-w-0 lg:sticky lg:top-4 lg:self-start">
        <ul className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
          {SECTIONS.map((s) => (
            <li key={s}>
              <button
                type="button"
                onClick={() => show(s)}
                aria-current={section === s ? "page" : undefined}
                className={`w-full whitespace-nowrap rounded px-3 py-2 text-left text-sm ${
                  section === s ? "bg-panel font-medium text-ink shadow-[inset_2px_0_0_var(--accent)]" : "text-ink-2 hover:bg-panel"
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
                <h1 className="text-xl font-semibold">{t.greeting(user.name)}</h1>
                {user.profile && (
                  <p className="text-sm text-ink-2">
                    {FIRM_TYPES[user.profile.firm_type]?.[lang]}, {SIZES[user.profile.size]?.[lang]}
                  </p>
                )}
              </div>
              <button type="button" onClick={props.onNewQuestion} className="rounded bg-accent px-4 py-2 text-sm font-medium text-accent-ink">
                {t.newQuestionCta}
              </button>
            </header>

            <dl className="grid grid-cols-[minmax(0,1fr)] gap-3 sm:grid-cols-3">
              <div className="rounded border border-line bg-panel px-4 py-3">
                <dt className="text-sm text-ink-2">{t.statQuestions}</dt>
                <dd className="mt-1 text-2xl font-semibold tabular-nums">{data?.stats.questions ?? "–"}</dd>
                <dd className="text-xs text-ink-3">{data ? t.statQuestions7d(data.stats.questions_7d) : ""}</dd>
              </div>
              <div className="rounded border border-line bg-panel px-4 py-3">
                <dt className="text-sm text-ink-2">{t.statObligations}</dt>
                <dd className="mt-1 text-2xl font-semibold tabular-nums">{data?.stats.obligations ?? "–"}</dd>
              </div>
              <div className="rounded border border-line bg-panel px-4 py-3">
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

            <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <section aria-labelledby="activity-title" className="rounded border border-line bg-panel px-4 py-3">
                <h2 id="activity-title" className="text-sm font-semibold">{t.activityTitle}</h2>
                <p className="mb-3 text-xs text-ink-3">{t.activitySub}</p>
                {data && <ActivityChart data={data.activity} lang={lang} tooltip={t.activityTooltip} label={t.activityTitle} />}
              </section>
              <section aria-labelledby="topics-title" className="rounded border border-line bg-panel px-4 py-3">
                <h2 id="topics-title" className="text-sm font-semibold">{t.regimesTitle}</h2>
                <p className="mb-3 text-xs text-ink-3">{t.regimesSub}</p>
                {data && (
                  <TopicBars rows={data.regimes.map((r) => ({ label: REGIMES[r.regime]?.[lang] ?? r.regime, count: r.count }))} empty={t.regimesEmpty} />
                )}
              </section>
            </div>

            <section aria-labelledby="recent-title">
              <div className="mb-2 flex items-baseline justify-between">
                <h2 id="recent-title" className="text-sm font-semibold">{t.recentTitle}</h2>
                <button type="button" onClick={() => show("questions")} className="text-sm text-accent underline underline-offset-2">
                  {t.showAll}
                </button>
              </div>
              <QuestionTable rows={data?.recent ?? []} t={t} lang={lang} timeFmt={timeFmt} topics={topics} onOpen={props.onOpenAnswer} />
            </section>
          </div>
        )}

        {section === "questions" && <QuestionsSection t={t} lang={lang} timeFmt={timeFmt} topics={topics} onOpen={props.onOpenAnswer} refreshKey={props.refreshKey} />}

        {section === "obligations" && <ObligationsSection t={t} timeFmt={timeFmt} onOpen={props.onOpenAnswer} refreshKey={props.refreshKey} />}

        {section === "dates" && <DatesSection t={t} lang={lang} user={user} dateFmt={dateFmt} />}

        {section === "account" && (
          <div className="flex max-w-[640px] flex-col gap-6">
            <h1 className="text-xl font-semibold">{t.accountTitle}</h1>
            <section aria-labelledby="acc-profile" className="rounded border border-line bg-panel px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <h2 id="acc-profile" className="text-sm font-semibold">{t.profile}</h2>
                <button type="button" onClick={props.onEditProfile} className="text-sm text-accent underline underline-offset-2">
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
            <section aria-labelledby="acc-account" className="rounded border border-line bg-panel px-4 py-3 text-sm">
              <h2 id="acc-account" className="font-semibold">{t.account}</h2>
              <p className="mt-2">
                <span className="text-ink-2">{t.signedInAs} </span>
                {user.name ? `${user.name}, ` : ""}
                {user.email}
              </p>
              <p className="mt-2 text-xs text-ink-3">{t.accountPrivacy}</p>
              <div className="mt-3 flex flex-wrap gap-4">
                <button type="button" onClick={props.onSignOut} className="rounded border border-line px-3 py-1.5 hover:border-ink-3">
                  {t.signOut}
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    if (!window.confirm(t.deleteConfirm)) return;
                    await deleteAccount();
                    props.onDeleted();
                  }}
                  className="text-red underline underline-offset-2"
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
  if (props.rows.length === 0) return <p className="rounded border border-line bg-panel px-4 py-3 text-sm text-ink-3">{props.empty ?? t.archiveEmpty}</p>;
  return (
    <div className="overflow-x-auto rounded border border-line bg-panel">
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
                </button>
              </td>
              <td className="px-4 py-2.5">
                <span className="flex flex-wrap gap-1">
                  {props.topics(r.regimes).map((name) => (
                    <span key={name} className="rounded-sm bg-panel-2 px-1.5 py-0.5 text-xs text-ink-2">{name}</span>
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
  topics: (r: string[]) => string[];
  onOpen: (id: string) => void;
  refreshKey: number;
}) {
  const { t } = props;
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<QuestionRow[] | null>(null);
  useEffect(() => {
    let current = true;
    const timer = setTimeout(() => {
      loadMyQuestions(search)
        .then((list) => current && setRows(list))
        .catch(() => current && setRows([]));
    }, 250);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [search, props.refreshKey]);
  return (
    <section aria-labelledby="questions-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 id="questions-title" className="text-xl font-semibold">{t.archive}</h1>
        <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t.archiveSearch} aria-label={t.archiveSearch}
          className="w-full rounded border border-line bg-panel px-3 py-1.5 text-sm sm:w-72" />
      </div>
      {rows && (
        <QuestionTable rows={rows} t={t} lang={props.lang} timeFmt={props.timeFmt} topics={props.topics} onOpen={props.onOpen}
          empty={search ? t.archiveNoMatch : t.archiveEmpty} />
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
    const blob = new Blob([csv(shown, header)], { type: "text/csv;charset=utf-8" });
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
          <h1 id="inventory-title" className="text-xl font-semibold">{t.inventoryTitle}</h1>
          <p className="max-w-[70ch] text-sm text-ink-2">{t.inventoryIntro}</p>
        </div>
        <div className="flex w-full flex-wrap items-center gap-3 sm:w-auto">
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t.inventorySearch} aria-label={t.inventorySearch}
            className="w-full rounded border border-line bg-panel px-3 py-1.5 text-sm sm:w-64" />
          {shown.length > 0 && (
            <button type="button" onClick={download} className="text-sm text-accent underline underline-offset-2">{t.downloadAll}</button>
          )}
        </div>
      </div>
      {rows && shown.length === 0 ? (
        <p className="rounded border border-line bg-panel px-4 py-3 text-sm text-ink-3">{search ? t.archiveNoMatch : t.inventoryEmpty}</p>
      ) : (
        <div className="overflow-x-auto rounded border border-line bg-panel">
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
        <h1 id="dates-title" className="text-xl font-semibold">{t.datesTitle}</h1>
        <p className="text-sm text-ink-2">{user.profile ? t.datesIntro : t.datesIntroAll}</p>
      </div>
      <ol className="rounded border border-line bg-panel">
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
