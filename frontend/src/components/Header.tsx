"use client";

import { FIRM_TYPES, SIZES, type Strings } from "@/lib/i18n";
import type { FirmProfile, Lang, ModelOption, User } from "@/lib/types";

type Theme = "system" | "light" | "dark";

export function Header(props: {
  t: Strings;
  lang: Lang;
  onLang: (l: Lang) => void;
  theme: Theme;
  onTheme: (t: Theme) => void;
  profile: FirmProfile | null;
  onEditProfile: () => void;
  models: ModelOption[];
  model: string;
  onModel: (id: string) => void;
  view: "research" | "dashboard";
  onView: (v: "research" | "dashboard") => void;
  user: User | null;
  onSignIn: () => void;
  onSignOut: () => void;
}) {
  const { t, lang, profile, models, model } = props;
  const current = models.find((m) => m.id === model);
  return (
    <header className="no-print border-b border-line bg-panel">
      <div className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 lg:px-6">
        <div className="min-w-0">
          <p className="text-[17px] font-semibold tracking-tight">{t.appName}</p>
          <p className="hidden text-xs text-ink-2 2xl:block">{t.tagline}</p>
        </div>

        <nav aria-label={t.appName} className="mr-auto flex gap-1 text-sm">
          {(["research", "dashboard"] as const).map((v) => (
            <a
              key={v}
              href={v === "research" ? "/" : "/dashboard"}
              onClick={(e) => {
                e.preventDefault();
                props.onView(v);
              }}
              aria-current={props.view === v ? "page" : undefined}
              className={`rounded px-2.5 py-1.5 ${props.view === v ? "bg-panel-2 font-medium" : "text-ink-2 hover:bg-panel-2"}`}
            >
              {v === "research" ? t.research : t.dashboard}
            </a>
          ))}
        </nav>

        <button
          type="button"
          onClick={props.onEditProfile}
          className="flex items-center gap-2 rounded border border-line px-3 py-1.5 text-sm hover:border-ink-3"
          aria-haspopup="dialog"
        >
          <span className="text-ink-2">{t.profile}:</span>
          <span className="font-medium">
            {profile ? `${FIRM_TYPES[profile.firm_type]?.[lang] ?? profile.firm_type}, ${SIZES[profile.size]?.[lang] ?? profile.size}` : t.noProfile}
          </span>
        </button>

        <label className="flex items-center gap-2 text-sm" title={current?.note?.[lang]}>
          <span className="text-ink-2">{t.model}</span>
          <select
            value={model}
            onChange={(e) => props.onModel(e.target.value)}
            className="min-w-[9rem] max-w-[14rem] rounded border border-line bg-panel px-2 py-1.5"
          >
            {models.length === 0 && <option value="">…</option>}
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
                {m.eu_hosted ? ` (${t.euHosted})` : ""}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-3 text-sm">
          <fieldset className="flex overflow-hidden rounded border border-line" aria-label={t.language}>
            {(["de", "en"] as const).map((l) => (
              <button
                key={l}
                type="button"
                onClick={() => props.onLang(l)}
                aria-pressed={lang === l}
                className={`px-2.5 py-1.5 ${lang === l ? "bg-ink text-panel" : "hover:bg-panel-2"}`}
              >
                {l.toUpperCase()}
              </button>
            ))}
          </fieldset>
          {props.user ? (
            <span className="flex items-center gap-2">
              <span className="max-w-[12rem] truncate text-ink-2" title={props.user.email}>
                {props.user.name || props.user.email}
              </span>
              <button type="button" onClick={props.onSignOut} className="rounded border border-line px-2.5 py-1.5 hover:border-ink-3">
                {t.signOut}
              </button>
            </span>
          ) : (
            <button type="button" onClick={props.onSignIn} className="rounded border border-accent px-2.5 py-1.5 font-medium text-accent hover:bg-accent-soft">
              {t.signIn}
            </button>
          )}
          <label className="flex items-center gap-1.5">
            <span className="sr-only">{t.theme}</span>
            <select
              value={props.theme}
              onChange={(e) => props.onTheme(e.target.value as Theme)}
              className="rounded border border-line bg-panel px-2 py-1.5"
              aria-label={t.theme}
            >
              <option value="system">{t.themeSystem}</option>
              <option value="light">{t.themeLight}</option>
              <option value="dark">{t.themeDark}</option>
            </select>
          </label>
        </div>
      </div>
    </header>
  );
}
