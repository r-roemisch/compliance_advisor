"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AnswerView } from "./AnswerView";
import { Composer } from "./Composer";
import { Header } from "./Header";
import { PassageList } from "./PassageList";
import { ProfileDialog } from "./ProfileDialog";
import { Progress } from "./Progress";
import { Sidebar } from "./Sidebar";
import { ToolCards } from "./ToolCards";
import { ApiError, askStream, loadAnswer, loadHistory, loadModels, loadPresets, loadSources } from "@/lib/api";
import { EXAMPLES, STRINGS } from "@/lib/i18n";
import { readStored, writeStored } from "@/lib/storage";
import type { AskResponse, FirmProfile, HistoryItem, Lang, ModelOption, Preset, SourceInfo, Stage } from "@/lib/types";

type Theme = "system" | "light" | "dark";

export default function App() {
  // Rendered only in the browser (see app/page.tsx), so stored preferences can seed the state.
  const [lang, setLang] = useState<Lang>(() => readStored<Lang>("lang", "de"));
  const [theme, setTheme] = useState<Theme>(() => readStored<Theme>("theme", "system"));
  const [profile, setProfile] = useState<FirmProfile | null>(() => readStored<FirmProfile | null>("profile", null));
  const [model, setModel] = useState("");
  const [presets, setPresets] = useState<Preset[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [stage, setStage] = useState<Stage | null>(null);
  const [tools, setTools] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const t = STRINGS[lang];

  // The lists the interface needs.
  useEffect(() => {
    const storedModel = readStored<string>("model", "");
    loadModels()
      .then((list) => {
        setModels(list);
        setModel(list.some((m) => m.id === storedModel) ? storedModel : (list[0]?.id ?? ""));
      })
      .catch(() => undefined);
    loadPresets().then(setPresets).catch(() => undefined);
    loadSources()
      .then(setSources)
      .catch((e: ApiError) => setError(e.status === 0 ? STRINGS.de.errorUnreachable : e.message));
    loadHistory().then(setHistory).catch(() => undefined);
  }, []);

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

  const applyProfile = (p: FirmProfile | null) => {
    setProfile(p);
    writeStored("profile", p);
    setProfileOpen(false);
  };

  const submit = useCallback(async () => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setError(null);
    setResult(null);
    setActive(null);
    setTools([]);
    setStage("search");
    try {
      await askStream(
        { question, profile, model: model || null },
        (event) => {
          if (event.stage === "done") {
            setResult(event.result);
            setStage(null);
            loadHistory().then(setHistory).catch(() => undefined);
          } else if (event.stage === "error") {
            setError(`${t.errorPrefix} ${event.detail}`);
            setStage(null);
          } else {
            setStage(event.stage);
            if (event.tools) setTools(event.tools);
          }
        },
        controller.signal,
      );
    } catch (e) {
      const err = e as ApiError;
      setError(err.status === 0 ? t.errorUnreachable : `${t.errorPrefix} ${err.message}`);
      setStage(null);
    }
  }, [question, profile, model, t]);

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
      setError((e as ApiError).message);
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
        models={models}
        model={model}
        onModel={chooseModel}
      />

      <div className="mx-auto grid w-full max-w-[1500px] flex-1 gap-6 px-4 py-5 lg:grid-cols-[250px_minmax(0,1fr)] lg:px-6">
        <Sidebar
          t={t}
          lang={lang}
          history={history}
          sources={sources}
          currentId={result?.id ?? null}
          onOpen={openStored}
          onNew={startNew}
        />

        <main id="main" className="order-1 min-w-0 lg:order-none">
          <Composer t={t} value={question} onChange={setQuestion} onSubmit={submit} busy={busy} />

          {error && (
            <div role="alert" className="mt-4 flex flex-wrap items-center gap-3 border-l-[3px] border-red bg-red-soft px-3 py-2 text-sm">
              <span>{error}</span>
              {question.trim().length >= 3 && (
                <button type="button" onClick={submit} className="font-medium text-red underline underline-offset-2">
                  {t.retry}
                </button>
              )}
            </div>
          )}

          <div className="mt-5">
            {busy && stage && <Progress t={t} lang={lang} stage={stage} tools={tools} />}

            {!busy && !result && (
              <section className="max-w-[70ch] py-2">
                <h1 className="text-xl font-semibold leading-snug">{t.emptyTitle}</h1>
                <p className="mt-2 text-ink-2">{t.emptyBody}</p>
                <h2 className="mt-5 text-sm font-semibold text-ink-2">{t.examplesTitle}</h2>
                <ul className="mt-2 flex flex-col gap-2">
                  {[...EXAMPLES[lang], ...EXAMPLES[lang === "de" ? "en" : "de"].slice(0, 1)].map((example) => (
                    <li key={example}>
                      <button
                        type="button"
                        onClick={() => {
                          setQuestion(example);
                          document.getElementById("question")?.focus();
                        }}
                        className="text-left text-sm text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
                      >
                        {example}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {result && (
              <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,460px)]">
                <div className="min-w-0">
                  <AnswerView t={t} lang={lang} result={result} active={highlighted} onCite={cite} onHover={setHover} />
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

      <footer className="border-t border-line bg-panel">
        <p className="mx-auto max-w-[1500px] px-4 py-3 text-xs text-ink-2 lg:px-6">
          <strong className="font-semibold text-ink">{t.noticeShort}.</strong> {t.notice}
        </p>
      </footer>

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
