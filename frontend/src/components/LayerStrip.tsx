import { LAYERS } from "@/lib/i18n";
import type { Lang, Passage } from "@/lib/types";
import { LayerGlyph } from "./LayerGlyph";

/** Which Regulatory Layers the answer's Passages come from, cited ones counted first. */
export function LayerStrip({ passages, cited, lang, label }: { passages: Passage[]; cited: number[]; lang: Lang; label: string }) {
  const rows = LAYERS.map((layer) => {
    const inLayer = passages.filter((p) => p.layer === layer.id);
    return { layer, total: inLayer.length, cited: inLayer.filter((p) => cited.includes(p.n)).length };
  }).filter((r) => r.total > 0);
  if (rows.length === 0) return null;
  return (
    <div className="mt-4 border-t border-line pt-3">
      <p className="mb-2 text-xs text-ink-2">{label}</p>
      <ul className="flex flex-wrap gap-x-5 gap-y-2">
        {rows.map(({ layer, total, cited: c }) => (
          <li key={layer.id} className="flex items-center gap-2 text-sm">
            <LayerGlyph layer={layer.id} lang={lang} />
            <span>{layer[lang]}</span>
            <span className="text-ink-3 tabular-nums">
              {c}/{total}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
