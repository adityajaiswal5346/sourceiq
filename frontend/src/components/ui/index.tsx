/**
 * DocuMind — UI Primitives
 * Linear/Vercel design language.
 * Zinc text scale. Indigo brand. Green/amber/red only for semantics.
 */

import type { HTMLAttributes, ReactNode } from "react";
import type { ConfidenceLabel } from "../../types/api";

// ── ConfidenceBadge ───────────────────────────────────────────────

const BADGE: Record<ConfidenceLabel, string> = {
  high:   "bg-success-bg   border-success-border   text-success-text",
  medium: "bg-warning-bg   border-warning-border   text-warning-text",
  low:    "bg-danger-bg    border-danger-border    text-danger-text",
};
const DOT: Record<ConfidenceLabel, string> = {
  high:   "bg-success",
  medium: "bg-warning",
  low:    "bg-danger",
};

export function ConfidenceBadge({
  label, score,
}: { label: ConfidenceLabel; score: number }) {
  const pct = Math.round(score * 100);
  return (
    <span role="status"
          aria-label={`${label} confidence, ${pct}%`}
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full
                      border text-xs font-medium ${BADGE[label]}`}>
      <span aria-hidden className={`w-1.5 h-1.5 rounded-full ${DOT[label]}`} />
      {label.charAt(0).toUpperCase() + label.slice(1)} · {pct}%
    </span>
  );
}

// ── QueryCounter ──────────────────────────────────────────────────

export function QueryCounter({
  remaining, limit,
}: { remaining: number; limit: number }) {
  const used    = limit - remaining;
  const pct     = (used / limit) * 100;
  const atLimit = remaining === 0;

  return (
    <div role="status"
         aria-label={`${remaining} of ${limit} queries remaining`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-ink-secondary">
          {atLimit ? "Limit reached" : `${remaining} of ${limit} remaining`}
        </span>
        <span className={`text-xs font-semibold ${
          atLimit ? "text-danger-text" : "text-brand-text"
        }`}>{used}/{limit} used</span>
      </div>
      <div className="h-1 bg-edge rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${
            atLimit ? "bg-danger" : pct >= 66 ? "bg-warning" : "bg-brand"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────

export function Skeleton({
  className = "", ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div role="status" aria-label="Loading…"
         className={`skeleton ${className}`} {...props} />
  );
}

// ── Spinner ───────────────────────────────────────────────────────

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
         fill="none" className="animate-spin-fast" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor"
              strokeWidth="2.5" strokeOpacity="0.12" />
      <path d="M12 2a10 10 0 0 1 10 10"
            stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

// ── Avatar ────────────────────────────────────────────────────────

export function Avatar({
  src, name, email, size = 28,
}: { src: string|null; name: string|null; email: string; size?: number }) {
  const initial = (name ?? email)[0]?.toUpperCase() ?? "?";
  if (src) {
    return <img src={src} alt={name ?? email} width={size} height={size}
                className="rounded-full object-cover"
                style={{ width: size, height: size }} />;
  }
  return (
    <div aria-label={name ?? email}
         className="rounded-full bg-brand-muted border border-brand-border
                    flex items-center justify-center flex-shrink-0
                    text-brand-text font-semibold"
         style={{ width: size, height: size, fontSize: size * 0.38 }}>
      {initial}
    </div>
  );
}

// ── EmptyState ────────────────────────────────────────────────────

export function EmptyState({
  icon, title, subtitle,
}: { icon: ReactNode; title: string; subtitle: string }) {
  return (
    <div className="flex flex-col items-center py-20 px-6 text-center">
      <div className="w-12 h-12 rounded-2xl border border-edge bg-surface
                      shadow-xs flex items-center justify-center mb-5
                      text-ink-tertiary text-xl">
        {icon}
      </div>
      <p className="text-md font-semibold text-ink mb-1.5">{title}</p>
      <p className="text-sm text-ink-secondary max-w-xs leading-relaxed">
        {subtitle}
      </p>
    </div>
  );
}
