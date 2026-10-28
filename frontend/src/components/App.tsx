"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AnswerView } from "./AnswerView";
import { AuthDialog } from "./AuthDialog";
import { Dashboard } from "./Dashboard";
import { Composer } from "./Composer";
import { Header } from "./Header";
import { Obligations } from "./Obligations";
import { PassageList } from "./PassageList";
import { ProfileDialog } from "./ProfileDialog";
import { Progress } from "./Progress";
import { Sidebar } from "./Sidebar";
import { ToolCards } from "./ToolCards";
import {
  ApiError,
  askStream,
  loadAnswer,
  loadHistory,
  loadMe,
  loadModels,
  setUnauthorizedHandler,
  loadPresets,
  loadSources,
  logout,
  saveProfile,
} from "@/lib/api";
import { EXAMPLES, REGIMES, STRINGS } from "@/lib/i18n";
import { readStored, validProfile, writeStored } from "@/lib/storage";
import type { AskResponse, FirmProfile, HistoryItem, Lang, ModelOption, Preset, SearchStrategy, SourceInfo, Stage, User } from "@/lib/types";

type Theme = "system" | "light" | "dark";
export type View = "research" | "dashboard";

const PATHS: Record<View, string> = { research: "/", dashboard: "/dashboard" };

export default function App({ initialView = "research" }: { initialView?: View }) {
  // Rendered only in the browser (see app/page.tsx), so stored preferences can seed the state.
  const [lang, setLang] = useState<Lang>(() => readStored<Lang>("lang", "de"));
  const [theme, setTheme] = useState<Theme>(() => readStored<Theme>("theme", "system"));
  const [profile, setProfile] = useState<FirmProfile | null>(() => validProfile(readStored("profile", null)));
  const [listError, setListError] = useState(false);
  const [model, setModel] = useState("");
  const [strategy, setStrategy] = useState<SearchStrategy>("vector");
  const [strategies, setStrategies] = useState<SearchStrategy[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [stage, setStage] = useState<Stage | null>(null);
  const [tools, setTools] = useState<string[]>([]);
  const [found, setFound] = useState<{ count: number; sources: string[] } | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [view, setView] = useState<View>(initialView);
  const [user, setUser] = useState<User | null>(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authKey, setAuthKey] = useState(0);
  // Each opening starts fresh on the tab the caller asked for ("Konto erstellen" or "Anmelden").
  const openAuth = (mode: "login" | "register" = "login") => {
    setAuthMode(mode);
    setAuthKey((k) => k + 1);
    setAuthOpen(true);
  };
  const [refreshKey, setRefreshKey] = useState(0);
  const abort = useRef<AbortController | null>(null);
  const t = STRINGS[lang];

  // The lists the interface needs.
  useEffect(() => {
    const storedModel = readStored<string>("model", "");
    const storedStrategy = readStored<string>("strategy", "");
    loadModels()
      .then(({ models: list, strategies: offered, default_strategy }) => {
        setModels(list);
        setModel(list.some((m) => m.id === storedModel) ? storedModel : (list[0]?.id ?? ""));
        setStrategies(offered);
        setStrategy(offered.find((s) => s === storedStrategy) ?? default_strategy);
      })
      .catch(() => undefined);
    loadPresets().then(setPresets).catch(() => undefined);
    loadSources()
      .then(setSources)
      .catch(() => setListError(true));
    loadHistory().then(setHistory).catch(() => undefined);
    loadMe()
      .then((me) => me && signedIn(me))
      .catch(() => undefined);
    // Back and forward buttons switch between Research and Dashboard.
    const onPop = () => setView(window.location.pathname.startsWith("/dashboard") ? "dashboard" : "research");
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const go = (next: View) => {
    setView(next);
    if (window.location.pathname !== PATHS[next]) window.history.pushState(null, "", PATHS[next]);
  };

  /** After login: the account's Firm Profile wins; a guest profile is kept if the account has none. */
  function signedIn(me: User) {
    setUser(me);
    setAuthOpen(false);
    const own = validProfile(me.profile);
    if (own) {
      setProfile(own);
    } else {
      const local = validProfile(readStored("profile", null));
      if (local) saveProfile(local).then(setUser).catch(() => undefined);
    }
    loadHistory().then(setHistory).catch(() => undefined);
    setResult(null);
    setRefreshKey((k) => k + 1);
  }

  const signOut = async () => {
    await logout().catch(() => undefined);
    signedOut();
  };

  function signedOut() {
    setUser(null);
    setResult(null);
    setProfile(validProfile(readStored("profile", null)));
    loadHistory().then(setHistory).catch(() => undefined);
    go("research");
  }

  // A 401 on an account call while signed in means the session ended elsewhere (expiry, logout
  // in another tab): show the person as a guest where they are. A guest's 401 means nothing.
  const sessionEndedRef = useRef(() => {});
  sessionEndedRef.current = () => {
    if (!user) return;
    setUser(null);
    setResult(null);
    setProfile(validProfile(readStored("profile", null)));
    loadHistory().then(setHistory).catch(() => undefined);
  };
  useEffect(() => {
    setUnauthorizedHandler(() => sessionEndedRef.current());
    return () => setUnauthorizedHandler(null);
  }, []);

  /** What to tell the person when a call failed: a translated message for the usual causes. */
  const describe = useCallback(
    (e: ApiError) => (e.status === 0 ? t.errorUnreachable : (t.httpErrors[e.status] ?? `${t.errorPrefix} ${e.message}`)),
    [t],
  );

  useEffect(() => {
    document.documentElement.lang = lang;
    writeStored("lang", lang);
  }, [lang]);

  useEffect(() => {
    if (theme === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    writeStored("theme", theme);
  }, [theme]);

  const chooseModel = (id: string) => {
    setModel(id);
    writeStored("model", id);
  };

  const chooseStrategy = (s: SearchStrategy) => {
    setStrategy(s);
    writeStored("strategy", s);
  };

  const applyProfile = (p: FirmProfile | null) => {
    setProfile(p);
    setProfileOpen(false);
    if (user) {
      saveProfile(p)
        .then((me) => {
          setUser(me);
          setRefreshKey((k) => k + 1);
        })
        .catch(() => undefined);
    } else {
      writeStored("profile", p);
    }
  };

  const submit = useCallback(async () => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setError(null);
    setResult(null);
    setActive(null);
    setTools([]);
    setFound(null);
    setDraft("");
    setStage("precheck");
    try {
      await askStream(
        { question, profile, model: model || null, strategy },
        (event) => {
          if (event.stage === "done") {
            setResult(event.result);
            setStage(null);
            loadHistory().then(setHistory).catch(() => undefined);
            setRefreshKey((k) => k + 1);
          } else if (event.stage === "found") {
            setFound({ count: event.count, sources: event.sources });
          } else if (event.stage === "delta") {
            setDraft((d) => d + event.text);
          } else if (event.stage === "error") {
            setError(t.httpErrors[event.status] ?? `${t.errorPrefix} ${event.detail}`);
            setStage(null);
          } else if (event.stage === "refused") {
            // the result that follows carries the refusal
          } else {
            setStage(event.stage);
            if (event.stage === "writing") setDraft("");
            if ("tools" in event && event.tools) setTools(event.tools);
          }
        },
        controller.signal,
      );
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 429 && err.retryAfter) {
        const when = new Date(Date.now() + err.retryAfter * 1000);
        const locale = lang === "de" ? "de-DE" : "en-GB";
        if (err.limit === "daily-cost") {
          setError(t.costCeiling(when.toLocaleString(locale, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })));
        } else {
          setError(t.rateLimited(when.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })));
        }
      } else {
        setError(describe(err));
      }
      setStage(null);
    }
  }, [question, profile, model, strategy, t, lang, describe]);

  const openStored = async (id: string) => {
    abort.current?.abort();
    setError(null);
    setStage(null);
    setActive(null);
    try {
      const stored = await loadAnswer(id);
      setResult(stored);
      setQuestion(stored.question);
    } catch (e) {
      setError(describe(e as ApiError));
    }
  };

  const startNew = () => {
    abort.current?.abort();
    setResult(null);
    setQuestion("");
    setStage(null);
    setError(null);
    document.getElementById("question")?.focus();
  };

  const cite = (n: number) => {
    setActive(n);
    const el = document.getElementById(`passage-${n}`);
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "nearest" });
    el?.focus({ preventScroll: true });
  };

  const highlighted = hover ?? active;
  const busy = stage !== null;
  const regimes = Object.keys(REGIMES).filter((r) => sources.some((s) => s.regime === r));

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:bg-panel focus:px-3 focus:py-2">
        {t.skip}
      </a>
      <Header
        t={t}
        lang={lang}
        onLang={setLang}
        theme={theme}
        onTheme={setTheme}
        profile={profile}
        onEditProfile={() => setProfileOpen(true)}
        view={view}
        onView={go}
        user={user}
        onSignIn={() => openAuth("login")}
        onSignOut={signOut}
      />

      {view === "dashboard" ? (
        <main id="main" className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-5 lg:px-6">
          <Dashboard
            t={t}
            lang={lang}
            user={user}
            refreshKey={refreshKey}
            onSignIn={() => openAuth("login")}
            onSignUp={() => openAuth("register")}
            onEditProfile={() => setProfileOpen(true)}
            onOpenAnswer={(id) => {
              go("research");
              openStored(id);
            }}
            onSignOut={signOut}
            onNewQuestion={() => {
              go("research");
              startNew();
            }}
            onAsk={(prepared) => {
              go("research");
              startNew();
              setQuestion(prepared);
              requestAnimationFrame(() => document.getElementById("question")?.focus());
            }}
            onDeleted={signedOut}
          />
        </main>
      ) : (

      <div className="mx-auto grid w-full max-w-[1500px] flex-1 gap-6 px-4 py-5 lg:grid-cols-[250px_minmax(0,1fr)] lg:px-6">
        <Sidebar
          t={t}
          lang={lang}
          history={history}
          sources={sources}
          currentId={result?.id ?? null}
          profile={profile}
          onOpen={openStored}
          onNew={startNew}
        />

        <main id="main" className="order-1 min-w-0 lg:order-none">
          <Composer
            t={t}
            lang={lang}
            value={question}
            onChange={setQuestion}
            onSubmit={submit}
            busy={busy}
            models={models}
            model={model}
            onModel={chooseModel}
            strategies={strategies}
            strategy={strategy}
            onStrategy={chooseStrategy}
          />

          {listError && (
            <p role="alert" className="mt-4 rounded-lg bg-red-soft px-4 py-2.5 text-sm">
              {t.listUnavailable}
            </p>
          )}

          {error && (
            <div role="alert" className="mt-4 flex flex-wrap items-center gap-3 rounded-lg bg-red-soft px-4 py-2.5 text-sm">
              <span>{error}</span>
              {question.trim().length >= 3 && (
                <button type="button" onClick={submit} className="font-medium text-red underline underline-offset-2">
                  {t.retry}
                </button>
              )}
            </div>
          )}

          <div className="mt-5">
            {busy && stage && (
              <Progress t={t} lang={lang} stage={stage} tools={tools} found={found} profileSet={profile !== null} draft={draft} />
            )}

            {!busy && !result && (
              <section className="max-w-[820px] pt-4">
                <h1 className="max-w-[24ch] text-[26px] font-semibold leading-[1.15] tracking-tight text-balance sm:text-[30px]">
                  {t.emptyTitle}
                </h1>
                <p className="mt-3 max-w-[62ch] text-ink-2">{t.emptyBody}</p>
                <p className="mt-2 max-w-[62ch] text-sm text-ink-3">{t.protectionNote}</p>
                {regimes.length > 0 && (
                  <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
                    <span className="text-ink-2">{t.coverage(sources.length, regimes.length)}</span>
                    {regimes.map((r) => (
                      <span key={r} className="rounded-full bg-track px-2.5 py-0.5 text-xs text-ink-2">
                        {REGIMES[r]?.[lang] ?? r}
                      </span>
                    ))}
                  </div>
                )}
                <h2 className="mt-8 text-sm font-semibold text-ink-2">{t.examplesTitle}</h2>
                <ul className="mt-3 grid gap-3 sm:grid-cols-2">
                  {[...EXAMPLES[lang], ...EXAMPLES[lang === "de" ? "en" : "de"].slice(0, 1)].map((example) => (
                    <li key={example}>
                      <button
                        type="button"
                        onClick={() => {
                          setQuestion(example);
                          document.getElementById("question")?.focus();
                        }}
                        className="h-full w-full rounded-xl border border-line bg-panel px-4 py-3 text-left text-sm leading-relaxed transition-colors hover:border-accent hover:text-accent"
                      >
                        {example}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {result && result.refusal && (
              <section aria-labelledby="refusal-title" className="rounded-xl border border-line bg-panel px-5 py-4">
                <p className="mb-3 border-b border-line pb-3 text-sm text-ink-2">{result.question}</p>
                <h2 id="refusal-title" className="text-base font-semibold">
                  {t.refusalTitle}
                </h2>
                <p className="mt-2 max-w-[70ch] text-sm text-ink-2">{t.refusalReasons[result.refusal]}</p>
                <p className="mt-2 max-w-[70ch] text-sm">{t.refusalHint}</p>
                <p className="mt-3 text-xs text-ink-3">{t.strategies[result.strategy ?? "vector"]} · {result.model}</p>
              </section>
            )}

            {result && !result.refusal && (
              <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,460px)]">
                <div className="min-w-0">
                  <AnswerView t={t} lang={lang} result={result} active={highlighted} onCite={cite} onHover={setHover} />
                  {result.id && <Obligations key={result.id} t={t} answerId={result.id} initial={result.obligations ?? null} onCite={cite} />}
                  <ToolCards t={t} lang={lang} tools={result.tools} />
                </div>
                <div className="min-w-0 xl:sticky xl:top-4 xl:max-h-[calc(100vh-2rem)] xl:overflow-y-auto xl:pr-1 print-full">
                  <PassageList t={t} lang={lang} passages={result.passages} cited={result.cited} active={highlighted} onHover={setHover} />
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
      )}

      <footer className="border-t border-line bg-panel">
        <p className="mx-auto max-w-[1500px] px-4 py-3 text-xs text-ink-2 lg:px-6">
          <strong className="font-semibold text-ink">{t.noticeShort}.</strong> {t.notice}
        </p>
      </footer>

      <AuthDialog key={authKey} open={authOpen} t={t} initialMode={authMode} onDone={signedIn} onClose={() => setAuthOpen(false)} />

      <ProfileDialog
        open={profileOpen}
        t={t}
        lang={lang}
        presets={presets}
        profile={profile}
        onApply={applyProfile}
        onClose={() => setProfileOpen(false)}
      />
    </div>
  );
}
