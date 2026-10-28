"use client";

import { useEffect, useState } from "react";

import { ApiError, createKey, loadKeys, revokeKey } from "@/lib/api";
import type { Strings } from "@/lib/i18n";
import type { ApiKey } from "@/lib/types";

/** API keys of the account (ask and Rule Checks only; shown once, revocable). */
export function KeysSection({ t, timeFmt }: { t: Strings; timeFmt: Intl.DateTimeFormat }) {
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [name, setName] = useState("");
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () =>
    loadKeys()
      .then((k) => {
        setKeys(k);
        setError(null);
      })
      .catch((e: ApiError) => setError(e.message));
  useEffect(() => {
    refresh();
  }, []);
  return (
    <section aria-labelledby="acc-keys" className="rounded-xl border border-line bg-panel px-5 py-4 text-sm">
      <h2 id="acc-keys" className="font-semibold">{t.keysTitle}</h2>
      <p className="mt-2 text-ink-2">{t.keysIntro}</p>
      <form
        className="mt-3 flex flex-wrap items-center gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!name.trim()) return;
          try {
            const created = await createKey(name.trim());
            setSecret(created.secret);
            setName("");
            refresh();
          } catch (err) {
            setError((err as ApiError).message);
          }
        }}
      >
        <label htmlFor="key-name" className="sr-only">{t.keyName}</label>
        <input id="key-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={t.keyName} maxLength={100} className="field max-w-[16rem] py-1.5" />
        <button type="submit" disabled={!name.trim()} className="btn btn-primary btn-sm">{t.keyCreate}</button>
      </form>
      {secret && (
        <div role="note" className="mt-3 rounded-lg bg-amber-soft px-3 py-2">
          <p className="font-medium">{t.keyShownOnce}</p>
          <code className="mt-1 block select-all break-all text-xs">{secret}</code>
          <p className="mt-1 text-xs text-ink-2">{t.keyUsage}</p>
        </div>
      )}
      {error && <p role="alert" className="mt-2 text-red">{error}</p>}
      {keys && keys.length === 0 && <p className="mt-3 text-ink-3">{t.keyNone}</p>}
      {keys && keys.length > 0 && (
        <ul className="mt-3 divide-y divide-line">
          {keys.map((k) => (
            <li key={k.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <span className="font-medium">{k.name}</span>
              <code className="text-xs text-ink-2">{k.prefix}…</code>
              <span className="text-xs text-ink-3">
                {k.last_used_at ? t.keyLastUsed(timeFmt.format(new Date(k.last_used_at))) : t.keyNeverUsed}
              </span>
              <button
                type="button"
                onClick={async () => {
                  try {
                    await revokeKey(k.id);
                    refresh();
                  } catch (e) {
                    setError((e as ApiError).message);
                  }
                }}
                className="btn btn-outline btn-sm ml-auto"
              >
                {t.keyRevoke}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
