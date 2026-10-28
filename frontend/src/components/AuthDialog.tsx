"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, login, register } from "@/lib/api";
import type { Strings } from "@/lib/i18n";
import type { User } from "@/lib/types";

export function AuthDialog(props: {
  open: boolean;
  t: Strings;
  initialMode?: "login" | "register";
  onDone: (user: User) => void;
  onClose: () => void;
}) {
  const { t } = props;
  const ref = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<"login" | "register">(props.initialMode ?? "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (props.open && !dialog.open) dialog.showModal();
    else if (!props.open && dialog.open) dialog.close();
  }, [props.open]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = mode === "login" ? await login(email, password) : await register(email, password, name);
      setPassword("");
      props.onDone(user);
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError.status === 0 ? t.errorUnreachable : (t.accountErrors[apiError.message] ?? apiError.message));
    } finally {
      setBusy(false);
    }
  };

  return (
    <dialog
      ref={ref}
      onClose={props.onClose}
      aria-labelledby="auth-title"
      className="m-auto w-[min(440px,calc(100vw-32px))] rounded-2xl border border-line bg-panel p-0 text-ink shadow-dialog backdrop:bg-[#0b141e]/50 backdrop:backdrop-blur-[2px]"
    >
      <form onSubmit={submit} className="flex flex-col gap-4 px-6 py-6">
        <div>
          <h2 id="auth-title" className="text-lg font-semibold">
            {mode === "login" ? t.signIn : t.signUp}
          </h2>
          <p className="mt-1 text-sm text-ink-2">{t.accountIntro}</p>
        </div>
        <div role="tablist" className="switch text-sm">
          {(["login", "register"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              onClick={() => {
                setMode(m);
                setError(null);
              }}
              className="flex-1 text-center"
            >
              {m === "login" ? t.haveAccount : t.needAccount}
            </button>
          ))}
        </div>
        {mode === "register" && (
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">{t.name}</span>
            <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength={200}
              className="field py-2" />
          </label>
        )}
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">{t.email}</span>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email"
            className="field py-2" />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">{t.password}</span>
          <input type="password" required minLength={mode === "register" ? 10 : undefined} value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            className="field py-2" />
          {mode === "register" && <span className="text-xs text-ink-3">{t.passwordHint}</span>}
        </label>
        {error && <p role="alert" className="rounded-lg bg-red-soft px-3 py-2 text-sm">{error}</p>}
        {mode === "register" && <p className="text-xs text-ink-3">{t.accountPrivacy}</p>}
        <div className="flex items-center gap-2">
          <button type="submit" disabled={busy} className="btn btn-primary">
            {mode === "login" ? t.signIn : t.signUp}
          </button>
          <button type="button" onClick={props.onClose} className="btn btn-quiet ml-auto">
            {t.cancel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
