"use client";

import { useState } from "react";

import { ApiError, extractObligations } from "@/lib/api";
import type { Strings } from "@/lib/i18n";
import type { ObligationRow } from "@/lib/types";

function toCsv(rows: ObligationRow[], header: string[]): string {
  const cell = (v: string) => `"${v.replace(/"/g, '""')}"`;
  const lines = [header.map(cell).join(";")].concat(
    rows.map((r) => [r.addressee, r.action, r.deadline, r.provision, r.link].map(cell).join(";")),
  );
  return "﻿" + lines.join("\r\n"); // BOM and semicolons: opens correctly in German Excel
}

export function Obligations(props: { t: Strings; answerId: string; initial: ObligationRow[] | null }) {
  const { t } = props;
  const [rows, setRows] = useState<ObligationRow[] | null>(props.initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setRows(await extractObligations(props.answerId));
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const download = () => {
    if (!rows) return;
    const blob = new Blob([toCsv(rows, t.obligationColumns)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `pflichten-${props.answerId.slice(0, 8)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section aria-labelledby="obligations-title" className="mt-6">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h2 id="obligations-title" className="text-sm font-semibold text-ink-2">
          {t.obligations}
        </h2>
        {rows === null ? (
          <button
            type="button"
            onClick={run}
            disabled={busy}
            className="no-print rounded border border-accent px-3 py-1 text-sm font-medium text-accent hover:bg-accent-soft disabled:opacity-50"
          >
            {busy ? t.extracting : t.extractObligations}
          </button>
        ) : (
          rows.length > 0 && (
            <button type="button" onClick={download} className="no-print text-sm text-accent underline underline-offset-2">
              {t.downloadCsv}
            </button>
          )
        )}
      </div>
      {rows === null && !busy && !error && <p className="text-sm text-ink-3">{t.obligationsHint}</p>}
      {error && <p className="text-sm text-red">{error}</p>}
      {rows !== null && rows.length === 0 && <p className="text-sm text-ink-3">{t.noObligations}</p>}
      {rows !== null && rows.length > 0 && (
        <div className="overflow-x-auto rounded border border-line bg-panel">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line text-left text-ink-2">
                {t.obligationColumns.slice(0, 4).map((h) => (
                  <th key={h} scope="col" className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-line align-top first:border-t-0">
                  <td className="px-3 py-2">{r.addressee}</td>
                  <td className="px-3 py-2">{r.action}</td>
                  <td className="px-3 py-2 text-ink-2">{r.deadline || "–"}</td>
                  <td className="px-3 py-2">
                    <a href={r.link} target="_blank" rel="noreferrer" className="provision whitespace-nowrap text-accent underline underline-offset-2">
                      {r.provision}
                    </a>
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
