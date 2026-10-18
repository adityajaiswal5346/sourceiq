import type { Citation } from "../types/api";

function conf(score: number) {
  if (score >= 0.7) return { badge: "text-success-text bg-success-bg border-success-border", dot: "bg-success" };
  if (score >= 0.4) return { badge: "text-warning-text bg-warning-bg border-warning-border", dot: "bg-warning" };
  return              { badge: "text-danger-text  bg-danger-bg  border-danger-border",  dot: "bg-danger"  };
}

export default function SourcePanel({ citations }: { citations: readonly Citation[] }) {
  if (!citations.length) return null;

  return (
    <section aria-label="Sources" className="mt-6 pt-5 border-t border-edge">
      <p className="label-caps mb-3">Sources</p>
      <ol className="space-y-2">
        {citations.map((c, i) => {
          const s = conf(c.confidence);
          return (
            <li key={`${c.citation}-${i}`}
                className="flex gap-3 px-4 py-3 rounded-xl border border-edge
                           bg-surface-subtle hover:bg-surface hover:border-edge-strong
                           hover:shadow-xs transition-all duration-150 cursor-default">

              {/* Index */}
              <div aria-hidden
                   className="w-5 h-5 rounded-full bg-brand flex items-center
                              justify-center flex-shrink-0 mt-0.5">
                <span className="text-white font-bold" style={{ fontSize: 9 }}>{i + 1}</span>
              </div>

              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink truncate">{c.source_file}</p>
                {c.heading_path && (
                  <p className="text-xs text-ink-tertiary mt-0.5 line-clamp-2 leading-relaxed">
                    {c.heading_path}
                    {c.page > 0 && <span className="text-ink-disabled"> · p.{c.page}</span>}
                  </p>
                )}
                <span className={`inline-flex items-center gap-1 mt-2 px-2 py-0.5
                                  rounded-full border text-2xs font-medium ${s.badge}`}>
                  <span className={`w-1 h-1 rounded-full ${s.dot}`} aria-hidden />
                  {Math.round(c.confidence * 100)}% relevance
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
