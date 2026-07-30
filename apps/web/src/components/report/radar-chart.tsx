"use client";

import { formatNumber } from "@/lib/format";
import type { Locale } from "@/i18n/routing";
import type { Bilingual } from "@/lib/api/types";

const SIZE = 260;
const CENTRE = SIZE / 2;
const RADIUS = 88;
const RINGS = 4;

/**
 * A profile across a handful of categories, as a polygon.
 *
 * Useful when the shape matters more than exact ranking — a role mix that is
 * lopsided looks lopsided here in a way a bar chart's ordering hides. Axis labels
 * sit outside the polygon with their values attached, so the figure never depends
 * on reading a position against a ring, which is the weakness of the form.
 *
 * Direction is fixed rather than inherited from the writing mode: a polygon that
 * mirrored under RTL would describe a different profile from the same numbers.
 */
export function RadarChart({
  title,
  categories,
  values,
  locale,
}: {
  title: Bilingual;
  categories: string[];
  values: number[];
  locale: string;
}) {
  const key = locale as Locale;
  const label = title[key] || title.en;
  const max = Math.max(...values, 0) || 1;
  const count = values.length;

  // Start at the top and go clockwise, the orientation the form is read in.
  const angleAt = (index: number) => (index / count) * 2 * Math.PI - Math.PI / 2;

  const pointAt = (index: number, fraction: number) => {
    const angle = angleAt(index);
    return {
      x: CENTRE + Math.cos(angle) * RADIUS * fraction,
      y: CENTRE + Math.sin(angle) * RADIUS * fraction,
    };
  };

  const polygon = values
    .map((value, index) => {
      const { x, y } = pointAt(index, value / max);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <figure
      role="img"
      aria-label={label}
      className="flex h-full flex-col rounded-lg border border-border bg-surface p-5"
    >
      <figcaption className="mb-2 text-sm font-medium">{label}</figcaption>

      <div dir="ltr" className="flex flex-1 items-center justify-center">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="h-auto w-full max-w-[17rem]">
          {/* Rings, so a reader can place a vertex without a numeric axis. */}
          {Array.from({ length: RINGS }, (_, ring) => {
            const fraction = (ring + 1) / RINGS;
            const ringPoints = Array.from({ length: count }, (_, index) => {
              const { x, y } = pointAt(index, fraction);
              return `${x.toFixed(1)},${y.toFixed(1)}`;
            }).join(" ");
            return (
              <polygon
                key={ring}
                points={ringPoints}
                fill="none"
                stroke="var(--grid)"
                strokeWidth="1"
              />
            );
          })}

          {/* Spokes. */}
          {values.map((_, index) => {
            const { x, y } = pointAt(index, 1);
            return (
              <line
                key={index}
                x1={CENTRE}
                y1={CENTRE}
                x2={x}
                y2={y}
                stroke="var(--grid)"
                strokeWidth="1"
              />
            );
          })}

          <polygon
            points={polygon}
            fill="var(--series-1)"
            fillOpacity="0.25"
            stroke="var(--series-1)"
            strokeWidth="2"
          />

          {values.map((value, index) => {
            const { x, y } = pointAt(index, value / max);
            return (
              <circle
                key={index}
                cx={x}
                cy={y}
                r="3"
                fill="var(--series-1)"
                stroke="var(--surface)"
                strokeWidth="1.5"
              />
            );
          })}
        </svg>
      </div>

      {/* The values in full, because a vertex against a ring is an estimate. */}
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {categories.map((category, index) => (
          <li key={`${category}-${index}`} className="flex items-center gap-1.5">
            <span className="text-muted">{category}</span>
            <span className="tabular-nums text-foreground">
              {formatNumber(values[index], locale)}
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
