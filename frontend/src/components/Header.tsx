"use client";

import { FIRM_TYPES, SIZES, type Strings } from "@/lib/i18n";
import type { FirmProfile, Lang, User } from "@/lib/types";
import { LayerMark } from "./LayerGlyph";

type Theme = "system" | "light" | "dark";
const NEXT_THEME: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };

function ThemeIcon({ theme }: { theme: Theme }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      {theme === "light" ? (
        <>
          <circle cx="8" cy="8" r="3" {...common} />
          <path d="M8 1.5v1.3M8 13.2v1.3M1.5 8h1.3M13.2 8h1.3M3.4 3.4l.9.9M11.7 11.7l.9.9M3.4 12.6l.9-.9M11.7 4.3l.9-.9" {...common} />
        </>
      ) : theme === "dark" ? (
        <path d="M13.5 10.2A6 6 0 0 1 5.8 2.5a6 6 0 1 0 7.7 7.7Z" {...common} />
      ) : (
        <>
          <rect x="1.75" y="2.5" width="12.5" height="8.5" rx="1.5" {...common} />
          <path d="M5.5 14h5M8 11v3" {...common} />
        </>
      )}
    </svg>
  );
}

function initials(user: User): string {
  const source = user.name?.trim() || user.email;
  const parts = source.split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (user.name?.trim() ? (parts[1]?.[0] ?? "") : "")).toUpperCase();
}

export function Header(props: {
  t: Strings;
  lang: Lang;
  onLang: (l: Lang) => void;
  theme: Theme;
  onTheme: (t: Theme) => void;
  profile: FirmProfile | null;
  onEditProfile: () => void;
  view: "research" | "dashboard";
  onView: (v: "research" | "dashboard") => void;
  user: User | null;
  onSignIn: () => void;
  onSignOut: () => void;
}) {
  const { t, lang, profile } = props;
  const themeLabel = { system: t.themeSystem, light: t.themeLight, dark: t.themeDark }[props.theme];
  const profileText = profile
    ? `${FIRM_TYPES[profile.firm_type]?.[lang] ?? profile.firm_type}, ${SIZES[profile.size]?.[lang] ?? profile.size}`
    : t.noProfile;
  return (
    <header className="no-print border-b border-line bg-panel">
      {/* Phone: brand with theme and account, then navigation and language, then the profile. Desktop: one row. */}
      <div className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-x-3 gap-y-2.5 px-4 py-2.5 lg:gap-x-4 lg:px-6">
        <div className="order-1 flex min-w-0 items-center gap-2.5 lg:mr-2">
          <LayerMark />
          <div className="min-w-0">
            <p className="text-[16px] font-semibold leading-tight tracking-tight">{t.appName}</p>
            <p className="hidden text-xs text-ink-2 2xl:block">{t.tagline}</p>
          </div>
        </div>

        <nav aria-label={t.appName} className="switch order-3 mr-auto text-sm lg:order-2">
          {(["research", "dashboard"] as const).map((v) => (
            <a
              key={v}
              href={v === "research" ? "/" : "/dashboard"}
              onClick={(e) => {
                e.preventDefault();
                props.onView(v);
              }}
              aria-current={props.view === v ? "page" : undefined}
            >
              {v === "research" ? t.research : t.dashboard}
            </a>
          ))}
        </nav>

        <button
          type="button"
          onClick={props.onEditProfile}
          className="chip order-5 max-w-full text-sm lg:order-3"
          aria-haspopup="dialog"
          aria-label={`${t.profile}: ${profileText}`}
        >
          <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${profile ? "bg-accent" : "border border-ink-3"}`} />
          {profile && <span className="hidden text-ink-2 xl:inline">{t.profile}</span>}
          <span className={`truncate ${profile ? "font-medium" : "text-ink-2"}`}>{profileText}</span>
        </button>

        <div role="group" aria-label={t.language} className="switch order-4 text-xs">
          {(["de", "en"] as const).map((l) => (
            <button key={l} type="button" onClick={() => props.onLang(l)} aria-pressed={lang === l} className="px-2.5">
              {l.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="order-2 ml-auto flex items-center gap-2 text-sm lg:order-5 lg:ml-0">
          <button
            type="button"
            onClick={() => props.onTheme(NEXT_THEME[props.theme])}
            className="btn btn-quiet p-2"
            aria-label={`${t.theme}: ${themeLabel}`}
            title={`${t.theme}: ${themeLabel}`}
          >
            <ThemeIcon theme={props.theme} />
          </button>

          {props.user ? (
            <span className="flex items-center gap-2">
              <span
                aria-hidden
                title={props.user.email}
                className="grid h-8 w-8 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent"
              >
                {initials(props.user)}
              </span>
              <span className="hidden max-w-[12rem] truncate text-ink-2 xl:inline" title={props.user.email}>
                {props.user.name || props.user.email}
              </span>
              <button type="button" onClick={props.onSignOut} className="btn btn-quiet">
                {t.signOut}
              </button>
            </span>
          ) : (
            <button type="button" onClick={props.onSignIn} className="btn btn-accent">
              {t.signIn}
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
