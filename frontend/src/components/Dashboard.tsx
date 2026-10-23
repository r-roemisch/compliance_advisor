"use client";

import { useEffect, useState } from "react";

import { ApiError, deleteAccount, loadDashboard, loadHistory } from "@/lib/api";
import { ACTIVITIES, CUSTOMERS, FIRM_TYPES, REGIMES, SIZES, type Strings } from "@/lib/i18n";
import type { DashboardData, HistoryItem, Lang, User } from "@/lib/types";

export function Dashboard(props: {
  t: Strings;
  lang: Lang;
  user: User | null;
  refreshKey: number;
  onSignIn: () => void;
  onEditProfile: () => void;
  onOpenAnswer: (id: string) => void;
  onSignedOut: () => void;
}) {
  const { t, lang, user } = props;
  const [data, setData] = useState<DashboardData | null>(null);
  const [search, setSearch] = useState("");
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dateFmt = new Intl.DateTimeFormat(lang === "de" ? "de-DE" : "en-GB", { day: "numeric", month: "short", year: "numeric" });
  const timeFmt = new Intl.DateTimeFormat(lang === "de" ? "de-DE" : "en-GB", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  const money = new Intl.NumberFormat(lang === "de" ? "de-DE" : "en-GB", { style: "currency", currency: "USD", maximumFractionDigits: 3 });

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

  useEffect(() => {
    if (!user) return;
    let current = true;
    const timer = setTimeout(() => {
      loadHistory(search)
        .then((list) => current && setItems(list))
        .catch(() => current && setItems([]));
    }, 250); // wait until typing pauses
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [user, search, props.refreshKey]);

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

  const remove = async () => {
    if (!window.confirm(t.deleteConfirm)) return;
    await deleteAccount();
    props.onSignedOut();
  };

  const profile = user.profile;
  const stats = data?.stats;
  return (
    <div className="flex flex-col gap-6 py-1">
      <header>
        <h1 className="text-xl font-semibold">{t.greeting(user.name)}</h1>
        <p className="text-sm text-ink-2">
          {user.email}
          {stats?.first_question_at && <> · {t.memberSince(dateFmt.format(new Date(stats.first_question_at)))}</>}
        </p>
      </header>
      {error && <p role="alert" className="text-sm text-red">{error}</p>}

      <dl className="grid gap-3 sm:grid-cols-3">
        {[
          { label: t.statQuestions, value: stats ? String(stats.questions) : "–" },
          { label: t.statObligations, value: stats ? String(stats.obligations) : "–" },
          { label: t.statCost, value: stats ? money.format(stats.cost_usd) : "–" },
        ].map((s) => (
          <div key={s.label} className="rounded border border-line bg-panel px-4 py-3">
            <dt className="text-sm text-ink-2">{s.label}</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{s.value}</dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        <section aria-labelledby="archive-title" className="min-w-0">
          <div className="mb-2 flex flex-wrap items-end justify-between gap-3">
            <h2 id="archive-title" className="text-sm font-semibold text-ink-2">{t.archive}</h2>
            <label className="w-full sm:w-72">
              <span className="sr-only">{t.archiveSearch}</span>
              <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t.archiveSearch}
                className="w-full rounded border border-line bg-panel px-3 py-1.5 text-sm" />
            </label>
          </div>
          <div className="rounded border border-line bg-panel">
            {items === null ? null : items.length === 0 ? (
              <p className="px-4 py-3 text-sm text-ink-3">{search ? t.archiveNoMatch : t.archiveEmpty}</p>
            ) : (
              <ul>
                {items.map((h) => (
                  <li key={h.id} className="border-t border-line first:border-t-0">
                    <button type="button" onClick={() => props.onOpenAnswer(h.id)}
                      className="flex w-full flex-col gap-0.5 px-4 py-2.5 text-left hover:bg-panel-2">
                      <span className="text-sm">{h.question}</span>
                      <span className="text-xs text-ink-3 tabular-nums">
                        {timeFmt.format(new Date(h.created_at))} · {h.model}
                        {h.has_obligations && <> · {t.withObligations}</>}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <div className="flex min-w-0 flex-col gap-6">
          <section aria-labelledby="dash-profile" className="rounded border border-line bg-panel px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <h2 id="dash-profile" className="text-sm font-semibold text-ink-2">{t.profile}</h2>
              <button type="button" onClick={props.onEditProfile} className="text-sm text-accent underline underline-offset-2">
                {profile ? t.editProfile : t.editProfileCta}
              </button>
            </div>
            {profile ? (
              <div className="mt-2 text-sm">
                <p className="font-medium">
                  {FIRM_TYPES[profile.firm_type]?.[lang]}, {SIZES[profile.size]?.[lang]}, {CUSTOMERS[profile.customers]?.[lang]}
                </p>
                <p className="mt-1 text-ink-2">{profile.activities.map((a) => ACTIVITIES[a]?.[lang] ?? a).join(", ") || "–"}</p>
              </div>
            ) : (
              <p className="mt-2 text-sm text-ink-3">{t.noProfile}</p>
            )}
          </section>

          <section aria-labelledby="dash-upcoming">
            <h2 id="dash-upcoming" className="mb-2 text-sm font-semibold text-ink-2">{profile ? t.upcoming : t.upcomingNoProfile}</h2>
            <ol className="rounded border border-line bg-panel text-sm">
              {(data?.upcoming ?? []).map((e, i) => (
                <li key={i} className="border-t border-line px-4 py-2 first:border-t-0">
                  <time dateTime={e.date} className="font-medium tabular-nums">{dateFmt.format(new Date(e.date))}</time>
                  <span className="ml-2 text-xs text-ink-3">{t.inDays(e.days_from_today)}</span>
                  <span className="block">
                    <a href={e.link} target="_blank" rel="noreferrer" className="provision hover:text-accent">{e.source}</a>{" "}
                    <span className="text-xs text-ink-3">{REGIMES[e.regime]?.[lang]}</span>
                  </span>
                  <span className="block text-ink-2">{e.what}</span>
                </li>
              ))}
            </ol>
          </section>

          <section aria-labelledby="dash-account" className="text-sm">
            <h2 id="dash-account" className="mb-2 font-semibold text-ink-2">{t.account}</h2>
            <p className="text-xs text-ink-3">{t.accountPrivacy}</p>
            <button type="button" onClick={remove} className="mt-2 text-red underline underline-offset-2">{t.deleteAccount}</button>
          </section>
        </div>
      </div>
    </div>
  );
}
