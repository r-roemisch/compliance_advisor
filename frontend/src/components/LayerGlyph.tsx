import { LAYERS } from "@/lib/i18n";
import type { Lang } from "@/lib/types";

/**
 * A five-step stack: EU Level 1 at the top, BaFin practice at the bottom. The Source's own
 * layer is drawn in ink; binding law solid, supervisory expectation outlined.
 */
export function LayerGlyph({ layer, lang, size = 16 }: { layer: string; lang: Lang; size?: number }) {
  const index = LAYERS.findIndex((l) => l.id === layer);
  const info = LAYERS[index];
  const label = info ? info[lang] : layer;
  return (
    <svg
      width={size * 0.875}
      height={size}
      viewBox="0 0 14 16"
      role="img"
      aria-label={label}
      className="shrink-0"
    >
      <title>{label}</title>
      {LAYERS.map((l, i) => {
        const active = i === index;
        const y = 1 + i * 3;
        return active ? (
          <rect
            key={l.id}
            x={0.75}
            y={y - 0.25}
            width={12.5}
            height={2.5}
            rx={0.5}
            fill={l.binding ? "var(--ink)" : "none"}
            stroke="var(--ink)"
            strokeWidth={1}
          />
        ) : (
          <rect key={l.id} x={3} y={y + 0.25} width={8} height={1.5} rx={0.5} fill="var(--line)" />
        );
      })}
    </svg>
  );
}

export function layerName(layer: string, lang: Lang): string {
  return LAYERS.find((l) => l.id === layer)?.[lang] ?? layer;
}

export function isBinding(layer: string): boolean {
  return LAYERS.find((l) => l.id === layer)?.binding ?? false;
}
