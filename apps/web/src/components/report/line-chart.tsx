"use client";

import { useId, useState } from "react";

import { formatNumber } from "@/lib/format";
import type { Locale } from "@/i18n/routing";
import type { Bilingual } from "@/lib/api/types";

const WIDTH = 640;
const HEIGHT = 220;
const PADDING = { top: 12, right: 16, bottom: 28, left: 44 };

/**
 * The plot area is locked to LTR even on a Persian page: time reads earliest-first
 * left to right, which is the convention Iranian analytics tools follow. Only the
 * surrounding prose flips.
 */
export function LineChart({
  title,
  labels,
  values,
  locale,
}: {
  title: Bilingual;
  labels: string[];
  values: number[];
  locale: string;
}) {
  const key = locale as Locale;
  const caption = title[key] || title.en;
  const gradientId = useId();
  const [hovered, setHovered] = useState<number | null>(null);

  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;

  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;

  const pointAt = (index: number) => ({
    x: PADDING.left + (values.length === 1 ? plotWidth / 2 : (index / (values.length - 1)) * plotWidth),
    y: PADDING.top + plotHeight - ((values[index] - min) / span) * plotHeight,
  });

  const path = values.map((_, index) => {
    const { x, y } = pointAt(index);
    return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");

  const ticks = [0, 0.5, 1].map((fraction) => ({
    value: min + span * fraction,
    y: PADDING.top + plotHeight - fraction * plotHeight,
  }));

  return (
    <figure
      role="img"
      aria-label={caption}
      className="rounded-lg border border-border bg-surface p-5"
    >
      <figcaption className="mb-3 text-sm font-medium">{caption}</figcaption>

      <div dir="ltr" className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-auto w-full min-w-[32rem]"
          onMouseLeave={() => setHovered(null)}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--series-1)" stopOpacity="0.18" />
              <stop offset="100%" stopColor="var(--series-1)" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Recessive grid: present enough to read a value against, quiet enough
              to stay behind the data. */}
          {ticks.map((tick) => (
            <g key={tick.y}>
              <line
                x1={PADDING.left}
                x2={WIDTH - PADDING.right}
                y1={tick.y}
                y2={tick.y}
                stroke="var(--grid)"
                strokeWidth="1"
              />
              <text
                x={PADDING.left - 8}
                y={tick.y + 3}
                textAnchor="end"
                className="fill-[var(--muted)] text-[10px] tabular-nums"
              >
                {formatNumber(Math.round(tick.value), locale)}
              </text>
            </g>
          ))}

          <path
            d={`${path} L ${pointAt(values.length - 1).x} ${PADDING.top + plotHeight} L ${pointAt(0).x} ${PADDING.top + plotHeight} Z`}
            fill={`url(#${gradientId})`}
          />
          <path d={path} fill="none" stroke="var(--series-1)" strokeWidth="2" />

          {values.map((value, index) => {
            const { x, y } = pointAt(index);
            return (
              <g key={index}>
                <circle
                  cx={x}
                  cy={y}
                  r={hovered === index ? 5 : 3.5}
                  fill="var(--series-1)"
                  stroke="var(--surface)"
                  strokeWidth="2"
                />
                {/* Hit target deliberately larger than the mark. */}
                <rect
                  x={x - 14}
                  y={PADDING.top}
                  width={28}
                  height={plotHeight}
                  fill="transparent"
                  onMouseEnter={() => setHovered(index)}
                />
              </g>
            );
          })}

          {hovered !== null ? (
            <g>
              <line
                x1={pointAt(hovered).x}
                x2={pointAt(hovered).x}
                y1={PADDING.top}
                y2={PADDING.top + plotHeight}
                stroke="var(--grid)"
                strokeWidth="1"
              />
              <text
                x={Math.min(pointAt(hovered).x + 8, WIDTH - PADDING.right - 60)}
                y={PADDING.top + 12}
                className="fill-[var(--foreground)] text-[11px] tabular-nums"
              >
                {labels[hovered]}: {formatNumber(values[hovered], locale)}
              </text>
            </g>
          ) : null}

          {labels.map((label, index) =>
            index === 0 || index === labels.length - 1 ? (
              <text
                key={label + index}
                x={pointAt(index).x}
                y={HEIGHT - 8}
                textAnchor={index === 0 ? "start" : "end"}
                className="fill-[var(--muted)] text-[10px]"
              >
                {label}
              </text>
            ) : null,
          )}
        </svg>
      </div>
    </figure>
  );
}
