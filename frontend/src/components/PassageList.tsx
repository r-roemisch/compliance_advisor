"use client";

import { LEGAL_STATUS, type Strings } from "@/lib/i18n";
import type { Lang, Passage } from "@/lib/types";
import { isBinding, LayerGlyph, layerName } from "./LayerGlyph";

/**
 * A Passage's text is "<provision> – <title> (part i of n)" on its first line, then the
 * Provision's own heading ("Article 19" + title, "§ 54 Title", "5.7 Title") on the first part.
 * The card already shows both, so the text starts after them.
 */
export function splitHeading(p: Passage): { body: string; part: string | null } {
  if (!p.provision) return { body: p.text, part: null };
  const lines = p.text.split("\n");
  const partMatch = lines[0].match(/\(part (\d+) of (\d+)\)/);
  let rest = lines[0].startsWith(p.provision) ? lines.slice(1) : lines;
  const label = p.provision.slice(0, p.provision.length - p.short_title.length).trim(); // "Art. 19", "§ 54", "5.7"
  const euHeading = label.replace(/^Art\. /, "Article ").replace(/^Annex /, "ANNEX ");
  const first = rest[0]?.trim() ?? "";
  if (first === euHeading || first.toUpperCase() === euHeading.toUpperCase()) {
    rest = rest.slice(1);
    if ((rest[0]?.trim() ?? "") === p.provision_title) rest = rest.slice(1);
  } else if (first.startsWith(label + " ") || first === label) {
    rest = rest.slice(1);
  }
  return { body: rest.join("\n").trim(), part: partMatch ? `${partMatch[1]}/${partMatch[2]}` : null };
}

export function PassageList(props: {
  t: Strings;
  lang: Lang;
  passages: Passage[];
  cited: number[];
  active: number | null;
  onHover: (n: number | null) => void;
}) {
  const { t, lang, passages, cited, active } = props;
  return (
    <section aria-labelledby="passages-title">
      <h2 id="passages-title" className="mb-2 text-sm font-semibold text-ink-2">
        {t.passages}
      </h2>
      <ol className="flex flex-col gap-3">
        {passages.map((p) => {
          const { body, part } = splitHeading(p);
          const isCited = cited.includes(p.n);
          const highlighted = active === p.n;
          const later = p.legal_status !== "in_force";
          return (
            <li
              key={p.passage_id}
              id={`passage-${p.n}`}
              tabIndex={-1}
              onMouseEnter={() => props.onHover(p.n)}
              onMouseLeave={() => props.onHover(null)}
              className={`scroll-mt-4 rounded-xl border bg-panel transition-colors ${
                highlighted ? "border-accent bg-mark" : "border-line"
              } ${isCited ? "" : "opacity-75"}`}
            >
              <div className="flex items-start gap-3 px-4 pt-3">
                <span
                  className={`mt-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-md px-1 text-[11px] font-semibold tabular-nums ${
                    isCited ? "bg-accent text-accent-ink" : "border border-line text-ink-2"
                  }`}
                >
                  {p.n}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="leading-snug">
                    <span className="provision text-[15px]">{p.provision || p.short_title}</span>
                    {p.provision_title && <span className="text-ink-2"> – {p.provision_title}</span>}
                    {part && <span className="text-ink-3"> ({part})</span>}
                  </p>
                  <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2">
                    <span className="inline-flex items-center gap-1.5">
                      <LayerGlyph layer={p.layer} lang={lang} size={14} />
                      {layerName(p.layer, lang)}
                      {!isBinding(p.layer) && <span className="text-ink-3">({t.supervisoryExpectation})</span>}
                    </span>
                    <span>{p.issuer}</span>
                    {later ? (
                      <span className="rounded-full bg-amber-soft px-2 font-medium text-amber">{LEGAL_STATUS[p.legal_status]?.[lang] ?? p.legal_status}</span>
                    ) : (
                      <span>{LEGAL_STATUS.in_force[lang]}</span>
                    )}
                    {p.as_of && <span>{t.asOf(p.as_of)}</span>}
                  </p>
                </div>
              </div>
              <blockquote className="legal print-full mx-4 mt-2 max-h-48 overflow-y-auto whitespace-pre-line border-l-2 border-line pl-3 text-ink">
                {body}
              </blockquote>
              <div className="flex flex-wrap items-center gap-x-4 px-4 py-2.5 text-xs text-ink-2">
                <a
                  href={p.link || p.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-accent underline underline-offset-2"
                >
                  {p.link ? t.openProvision : t.openSource}
                  <span className="sr-only"> {p.provision}</span>
                </a>
                <span>{isCited ? t.cited : t.notCited}</span>
                <span className="tabular-nums">{t.similarity(p.score.toFixed(2))}</span>
                {p.version && <span className="text-ink-3">{p.version}</span>}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
