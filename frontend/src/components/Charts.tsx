"use client";

import { useState } from "react";

import type { Lang } from "@/lib/types";

/**
 * Questions per day: one series, so no legend; the card title names it. Columns are at most
 * 24px wide with a 4px rounded top, square at the baseline, 2px apart; colour is the validated
 * chart token. Every column has a hover/focus tooltip, and a table carries the same data for
 * screen readers. A day with questions is a button that opens them.
 */
export function ActivityChart(props: {
  data: { date: string; count: number }[];
  lang: Lang;
  tooltip: (n: number) => string;
  label: string;
  onSelect?: (date: string) => void;
}) {
  const { data, lang } = props;
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...data.map((d) => d.count));
  const top = max <= 4 ? max : Math.ceil(max / 5) * 5; // a clean top tick
  const day = new Intl.DateTimeFormat(lang === "de" ? "de-DE" : "en-GB", { day: "numeric", month: "short" });
  const ticks = [0, Math.floor(data.length / 2), data.length - 1];

  return (
    <figure className="m-0">
      <div className="relative grid grid-cols-[auto_1fr] gap-x-2">
        <div className="flex h-36 flex-col justify-between text-right text-xs text-ink-3 tabular-nums" aria-hidden>
          <span>{top}</span>
          <span>0</span>
        </div>
        <div className="relative h-36 border-b border-t border-line" onMouseLeave={() => setHover(null)}>
          <div className="absolute inset-0 flex items-end gap-[2px] px-[2px]">
            {data.map((d, i) => {
              const clickable = props.onSelect !== undefined && d.count > 0;
              const Column = clickable ? "button" : "div";
              return (
              <Column
                key={d.date}
                className={`relative flex h-full min-w-0 flex-1 items-end justify-center ${clickable ? "cursor-pointer" : ""}`}
                onMouseEnter={() => setHover(i)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                onClick={clickable ? () => props.onSelect?.(d.date) : undefined}
                {...(clickable ? { type: "button" as const } : { "aria-hidden": true })}
                aria-label={`${day.format(new Date(d.date))}: ${props.tooltip(d.count)}`}
              >
                {d.count > 0 && (
                  <div
                    className="w-full max-w-[24px] rounded-t-[4px] bg-chart"
                    style={{ height: `${(d.count / top) * 100}%`, opacity: hover === null || hover === i ? 1 : 0.55 }}
                  />
                )}
                {hover === i && (
                  <div className="pointer-events-none absolute bottom-full z-10 mb-1 whitespace-nowrap rounded-lg border border-line bg-panel px-2.5 py-1.5 text-xs shadow-[0_4px_12px_-4px_var(--shadow)]">
                    <span className="block text-ink-2">{day.format(new Date(d.date))}</span>
                    <span className="font-semibold tabular-nums">{props.tooltip(d.count)}</span>
                  </div>
                )}
              </Column>
              );
            })}
          </div>
        </div>
        <div />
        <div className="mt-1 flex justify-between text-xs text-ink-3" aria-hidden>
          {ticks.map((i) => (
            <span key={i}>{data[i] ? day.format(new Date(data[i].date)) : ""}</span>
          ))}
        </div>
      </div>
      <table className="sr-only">
        <caption>{props.label}</caption>
        <tbody>
          {data.map((d) => (
            <tr key={d.date}>
              <th scope="row">{d.date}</th>
              <td>{d.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/**
 * Horizontal bars, sorted, value at the tip. One series: no legend. With onSelect, each row is a
 * button that opens the questions behind it.
 */
export function TopicBars(props: {
  rows: { id: string; label: string; count: number }[];
  empty: string;
  onSelect?: (id: string) => void;
  selectLabel?: (label: string) => string;
}) {
  if (props.rows.length === 0) return <p className="text-sm text-ink-3">{props.empty}</p>;
  const max = Math.max(...props.rows.map((r) => r.count));
  return (
    <ul className="flex flex-col gap-1">
      {props.rows.map((r) => {
        const content = (
          <>
            <span className="truncate text-left text-ink-2" title={r.label}>
              {r.label}
            </span>
            <span className="flex items-center gap-2">
              <span className="block h-3 rounded-r-[4px] bg-chart" style={{ width: `calc((100% - 2.5rem) * ${r.count / max})` }} />
              <span className="tabular-nums text-ink">{r.count}</span>
            </span>
          </>
        );
        const row = "grid w-full grid-cols-[minmax(7rem,9rem)_1fr] items-center gap-3 rounded-lg px-2 py-1.5 text-sm";
        return (
          <li key={r.id}>
            {props.onSelect ? (
              <button
                type="button"
                onClick={() => props.onSelect?.(r.id)}
                aria-label={`${props.selectLabel?.(r.label) ?? r.label}: ${r.count}`}
                className={`${row} transition-colors hover:bg-panel-2`}
              >
                {content}
              </button>
            ) : (
              <div className={row} title={`${r.label}: ${r.count}`}>
                {content}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
