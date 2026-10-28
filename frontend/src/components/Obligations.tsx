"use client";

import { useState } from "react";

import { ApiError, extractObligations } from "@/lib/api";
import { toCsv } from "@/lib/csv";
import type { Strings } from "@/lib/i18n";
import type { ObligationRow } from "@/lib/types";

export function Obligations(props: { t: Strings; answerId: string; initial: ObligationRow[] | null; onCite?: (n: number) => void }) {
  const { t } = props;
  const [rows, setRows] = useState<ObligationRow[] | null>(props.initial);
  const [cost, setCost] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const extracted = await extractObligations(props.answerId);
      setRows(extracted.rows);
      setCost(extracted.cost_usd);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const download = () => {
    if (!rows) return;
    const blob = new Blob([toCsv(t.obligationColumns, rows.map((r) => [r.addressee, r.action, r.deadline, r.provision, r.link]))], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${t.obligationsFile}-${props.answerId.slice(0, 8)}.csv`;
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
            className="no-print btn btn-accent btn-sm"
          >
            {busy ? t.extracting : t.extractObligations}
          </button>
        ) : (
          rows.length > 0 && (
            <button type="button" onClick={download} className="no-print btn btn-outline btn-sm">
              {t.downloadCsv}
            </button>
          )
        )}
      </div>
      {rows === null && !busy && !error && <p className="text-sm text-ink-3">{t.obligationsHint}</p>}
      {error && <p className="text-sm text-red">{error}</p>}
      {cost > 0 && <p className="mb-2 text-xs text-ink-3 tabular-nums">{t.extractionCost(cost < 0.01 ? cost.toFixed(4) : cost.toFixed(3))}</p>}
      {rows !== null && rows.length === 0 && <p className="text-sm text-ink-3">{t.noObligations}</p>}
      {rows !== null && rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-line bg-panel">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line text-left text-ink-2">
                {[...t.obligationColumns.slice(0, 4), t.citationColumn].map((h) => (
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
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => props.onCite?.(r.passage)}
                      aria-label={`${t.passages} ${r.passage}`}
                      className="inline-flex h-[1.25rem] min-w-[1.25rem] items-center justify-center rounded-md border border-accent/50 px-1 text-[11px] font-semibold text-accent tabular-nums hover:bg-accent-soft"
                    >
                      {r.passage}
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
