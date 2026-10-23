"use client";

import { useEffect, useState } from "react";

import { loadTimeline } from "@/lib/api";
import { REGIMES, type Strings } from "@/lib/i18n";
import type { FirmProfile, Lang, TimelineEntry } from "@/lib/types";

export function TimelinePanel({ t, lang, profile }: { t: Strings; lang: Lang; profile: FirmProfile | null }) {
  const [upcoming, setUpcoming] = useState(true);
  const [forProfile, setForProfile] = useState(true);
  const [entries, setEntries] = useState<TimelineEntry[] | null>(null);
  const useProfile = forProfile && profile !== null;

  useEffect(() => {
    let current = true;
    loadTimeline(useProfile ? profile : null, upcoming)
      .then((list) => current && setEntries(list))
      .catch(() => current && setEntries([]));
    return () => {
      current = false;
    };
  }, [profile, upcoming, useProfile]);

  const fmt = new Intl.DateTimeFormat(lang === "de" ? "de-DE" : "en-GB", { day: "numeric", month: "short", year: "numeric" });
  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="flex flex-col gap-1.5">
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={upcoming} onChange={(e) => setUpcoming(e.target.checked)} />
          {t.upcomingOnly}
        </label>
        <label className={`inline-flex items-center gap-2 ${profile ? "" : "text-ink-3"}`}>
          <input type="checkbox" checked={useProfile} disabled={!profile} onChange={(e) => setForProfile(e.target.checked)} />
          {t.forProfile}
        </label>
      </div>
      {entries === null ? null : entries.length === 0 ? (
        <p className="text-ink-3">{t.noMilestones}</p>
      ) : (
        <ol className="flex flex-col">
          {entries.map((e, i) => (
            <li key={i} className={`border-t border-line py-2 first:border-t-0 ${e.status === "past" ? "text-ink-3" : ""}`}>
              <time dateTime={e.date} className="block font-medium tabular-nums">
                {fmt.format(new Date(e.date))}
                {e.status === "upcoming" && <span className="ml-2 text-xs font-normal text-ink-3">{t.inDays(e.days_from_today)}</span>}
              </time>
              <a href={e.link} target="_blank" rel="noreferrer" className="provision hover:text-accent">
                {e.source}
              </a>{" "}
              <span className="text-xs text-ink-3">{REGIMES[e.regime]?.[lang]}</span>
              <span className="block text-ink-2">{e.what}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
