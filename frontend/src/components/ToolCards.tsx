"use client";

import { APPLIES, CRITERIA, REGIMES, TOOL_NAMES, VERDICTS, type Strings } from "@/lib/i18n";
import type { Lang, Ref, ToolRun } from "@/lib/types";

function RefLinks({ refs }: { refs?: Ref[] }) {
  if (!refs?.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-x-2">
      {refs.map((r) =>
        r.link ? (
          <a key={r.provision} href={r.link} target="_blank" rel="noreferrer" className="provision text-accent underline underline-offset-2">
            {r.provision}
          </a>
        ) : (
          <span key={r.provision} className="provision">
            {r.provision}
          </span>
        ),
      )}
    </span>
  );
}

function Missing({ t, items }: { t: Strings; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="mt-3 rounded-lg bg-amber-soft px-3 py-2 text-sm">
      <p className="font-medium text-amber">{t.missingFacts}</p>
      <ul className="mt-1 list-disc pl-5 text-ink">
        {items.map((m) => (
          <li key={m}>{m}</li>
        ))}
      </ul>
    </div>
  );
}

const tone: Record<string, string> = {
  yes: "text-ink font-semibold",
  applies: "text-ink font-semibold",
  no: "text-ink-3",
  check: "text-amber font-semibold",
  later: "text-accent font-semibold",
  not_in_corpus: "text-ink-3 italic",
};

function Applicability({ r, lang }: { r: Record<string, unknown>; lang: Lang }) {
  const findings = (r.findings as { regime: string; applies: string; reason: string; provisions: Ref[] }[]) ?? [];
  return (
    <table className="w-full border-collapse text-sm">
      <tbody>
        {findings.map((f) => (
          <tr key={f.regime} className="border-t border-line align-top first:border-t-0">
            <th scope="row" className="w-[28%] py-2 pr-3 text-left font-medium">
              {f.regime}
            </th>
            <td className={`w-[16%] py-2 pr-3 ${tone[f.applies] ?? ""}`}>{APPLIES[f.applies]?.[lang] ?? f.applies}</td>
            <td className="py-2 text-ink-2">
              {f.reason} <RefLinks refs={f.provisions} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Timeline({ r, lang }: { r: Record<string, unknown>; lang: Lang }) {
  const entries = (r.entries as { date: string; status: string; days_from_today: number; source: string; regime: string; what: string; link: string }[]) ?? [];
  const fmt = new Intl.DateTimeFormat(lang === "de" ? "de-DE" : "en-GB", { day: "numeric", month: "short", year: "numeric" });
  return (
    <ol className="text-sm">
      {entries.map((e, i) => (
        <li key={i} className={`grid grid-cols-[7.5rem_1fr] gap-3 border-t border-line py-1.5 first:border-t-0 ${e.status === "past" ? "text-ink-3" : ""}`}>
          <time dateTime={e.date} className="tabular-nums">
            {fmt.format(new Date(e.date))}
          </time>
          <span>
            <a href={e.link} target="_blank" rel="noreferrer" className="provision underline-offset-2 hover:underline">
              {e.source}
            </a>{" "}
            <span className="text-ink-3">({REGIMES[e.regime]?.[lang] ?? e.regime})</span>: {e.what}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Incident({ r, t, lang }: { r: Record<string, unknown>; t: Strings; lang: Lang }) {
  const major = String(r.major);
  const criteria = (r.criteria as { criterion: string; met: boolean | null; detail: string }[]) ?? [];
  const deadlines = (r.deadlines as string[]) ?? [];
  return (
    <div className="text-sm">
      <p className="text-base">
        {t.majorIncident}:{" "}
        <strong className={major === "yes" ? "text-red" : major === "undetermined" ? "text-amber" : "text-ink"}>
          {VERDICTS[major]?.[lang] ?? major}
        </strong>
      </p>
      <p className="mt-1 text-ink-2">{String(r.reason)}</p>
      <ul className="mt-3">
        {criteria.map((c) => (
          <li key={c.criterion} className="grid grid-cols-[1.25rem_1fr] gap-2 border-t border-line py-1.5 first:border-t-0">
            <span aria-hidden className={c.met ? "text-red" : c.met === false ? "text-ink-3" : "text-amber"}>
              {c.met ? "●" : c.met === false ? "○" : "?"}
            </span>
            <span>
              <span className="font-medium">{CRITERIA[c.criterion]?.[lang] ?? c.criterion}</span>
              <span className="sr-only">{c.met ? t.criterionMet : c.met === false ? t.criterionNotMet : t.criterionUnknown}</span>
              <span className="block text-xs text-ink-2">{c.detail}</span>
            </span>
          </li>
        ))}
      </ul>
      {deadlines.length > 0 && (
        <>
          <p className="mt-3 font-medium">{t.deadlines}</p>
          <ul className="mt-1 list-disc pl-5">
            {deadlines.map((d) => (
              <li key={d} className={d.startsWith("Initial notification due by") ? "font-semibold text-red" : ""}>
                {d}
              </li>
            ))}
          </ul>
        </>
      )}
      <Missing t={t} items={r.missing as string[]} />
      <p className="mt-3 text-xs">
        <RefLinks refs={r.provisions as Ref[]} />
      </p>
    </div>
  );
}

function AIUse({ r, t, lang }: { r: Record<string, unknown>; t: Strings; lang: Lang }) {
  const risk = String(r.risk_class);
  const duties = (r.duties as { duty: string; provision: Ref }[]) ?? [];
  return (
    <div className="text-sm">
      <p className="text-base">
        {t.riskClass}: <strong className={risk === "high_risk" ? "text-red" : "text-ink"}>{VERDICTS[risk]?.[lang] ?? risk}</strong>
      </p>
      <p className="mt-1 text-ink-2">{String(r.reason)}</p>
      {duties.length > 0 && (
        <>
          <p className="mt-3 font-medium">{t.duties}</p>
          <ul className="mt-1">
            {duties.map((d) => (
              <li key={d.duty} className="border-t border-line py-1.5 first:border-t-0">
                {d.duty} <RefLinks refs={[d.provision]} />
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="mt-3">
        <span className="font-medium">{t.appliesFrom}: </span>
        {((r.applies_from as string[]) ?? []).join(" ")}
      </p>
      <Missing t={t} items={r.missing as string[]} />
      <p className="mt-3 text-xs">
        <RefLinks refs={r.provisions as Ref[]} />
      </p>
    </div>
  );
}

export function ToolCards({ t, lang, tools }: { t: Strings; lang: Lang; tools: ToolRun[] }) {
  if (tools.length === 0) return null;
  return (
    <section aria-labelledby="checks-title" className="mt-6">
      <h2 id="checks-title" className="mb-2 text-sm font-semibold text-ink-2">
        {t.ruleChecks}
      </h2>
      <div className="flex flex-col gap-3">
        {tools.map((run, i) => (
          <article key={i} className="overflow-hidden rounded-xl border border-line bg-panel">
            <h3 className="border-b border-line bg-panel-2 px-4 py-2.5 text-sm font-semibold">{TOOL_NAMES[run.name]?.[lang] ?? run.name}</h3>
            <div className="px-4 py-3">
              {"error" in run.result ? (
                <p className="text-sm text-red">{String(run.result.error)}</p>
              ) : run.name === "check_applicability" ? (
                <Applicability r={run.result} lang={lang} />
              ) : run.name === "compliance_timeline" ? (
                <Timeline r={run.result} lang={lang} />
              ) : run.name === "classify_dora_incident" ? (
                <Incident r={run.result} t={t} lang={lang} />
              ) : run.name === "check_ai_act_use_case" ? (
                <AIUse r={run.result} t={t} lang={lang} />
              ) : (
                <pre className="overflow-x-auto text-xs">{JSON.stringify(run.result, null, 2)}</pre>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
