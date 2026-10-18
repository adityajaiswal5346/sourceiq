/**
 * Sourciq — QueryInterface
 *
 * Design: Linear light mode. Pure white sidebar. Surface-subtle main area.
 * Indigo accent surgically applied. Maximum whitespace. Typography-first.
 * No decorative elements — every pixel serves a function.
 */

import { useCallback, useRef, useState, type KeyboardEvent } from "react";
import { ApiError, api } from "../api/client";
import { Avatar, ConfidenceBadge, EmptyState, QueryCounter, Skeleton, Spinner } from "./ui";
import Footer from "./Footer";
import SourcePanel from "./SourcePanel";
import { useAuth } from "../context/AuthContext";
import type { Namespace, QueryResponse, QueryStatus } from "../types/api";

// Replace these two constants in frontend/src/components/QueryInterface.tsx
// Only kubernetes-docs namespace has data — remove Stripe and AWS

const NAMESPACES: { value: Namespace; label: string; sub: string }[] = [
  {
    value: "kubernetes-docs",
    label: "Kubernetes Docs",
    sub:   "Pods, ConfigMaps, workloads",
  },
  {
    value: "default",
    label: "All collections",
    sub:   "Search across everything",
  },
  // Stripe API and AWS WAF removed — not yet indexed.
  // Re-add when corpus is expanded in a later sprint.
];

// These questions are drawn directly from pods.md and configmaps.md
// — the only two files fully indexed. All should score >70%.
const EXAMPLES: string[] = [
  "What is a Kubernetes Pod and how does it differ from a container?",
  "How do I use a ConfigMap to pass configuration to a Pod?",
  "What is terminationGracePeriodSeconds and what is its default value?",
];

// ── Sidebar ───────────────────────────────────────────────────────

function Sidebar({
  namespace, onNamespace,
  queriesRemaining, queryLimit,
  user, onSignOut,
}: {
  namespace: Namespace;
  onNamespace: (n: Namespace) => void;
  queriesRemaining: number;
  queryLimit: number;
  user: { name: string|null; email: string; avatar_url: string|null };
  onSignOut: () => void;
}) {
  return (
    <aside className="w-[220px] flex-shrink-0 bg-surface border-r border-edge
                      flex flex-col h-full" aria-label="Navigation">

      {/* Wordmark */}
      <div className="h-[52px] px-4 flex items-center border-b border-edge">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 bg-brand rounded-md flex items-center
                          justify-center flex-shrink-0">
            <span className="text-white font-bold" style={{ fontSize: 11 }}>S</span>
          </div>
          <span className="text-base font-semibold text-ink tracking-tight">
            Sourciq
          </span>
        </div>
      </div>

      {/* Nav items */}
      <nav className="flex-1 overflow-y-auto scrollbar-none px-2 py-3">
        <p className="label-caps px-2 mb-2">Collections</p>
        <ul role="list" className="space-y-px">
          {NAMESPACES.map(n => (
            <li key={n.value}>
              <button
                onClick={() => onNamespace(n.value)}
                aria-current={namespace === n.value ? "page" : undefined}
                className={`w-full text-left px-2.5 py-2 rounded-lg flex items-start
                            gap-2 transition-colors duration-100 group ${
                  namespace === n.value
                    ? "bg-brand-muted text-brand-text"
                    : "text-ink-secondary hover:bg-surface-muted hover:text-ink"
                }`}
              >
                <div className={`w-1 h-1 rounded-full mt-2 flex-shrink-0 ${
                  namespace === n.value ? "bg-brand" : "bg-edge-strong"
                }`} aria-hidden />
                <div className="min-w-0">
                  <p className="text-sm font-medium leading-tight truncate">
                    {n.label}
                  </p>
                  <p className={`text-2xs mt-0.5 truncate ${
                    namespace === n.value ? "text-brand" : "text-ink-disabled"
                  }`}>
                    {n.sub}
                  </p>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* Usage */}
      <div className="px-4 py-4 border-t border-edge">
        <QueryCounter remaining={queriesRemaining} limit={queryLimit} />
        {queriesRemaining === 0 && (
          <p className="text-2xs text-ink-tertiary mt-2 leading-relaxed">
            Lifetime limit reached.
          </p>
        )}
      </div>

      {/* User row */}
      <div className="px-4 py-3 border-t border-edge flex items-center gap-2.5">
        <Avatar src={user.avatar_url} name={user.name} email={user.email} size={26} />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-ink truncate">
            {user.name ?? user.email}
          </p>
          <button onClick={onSignOut}
                  className="text-2xs text-ink-tertiary hover:text-brand
                             transition-colors">
            Sign out
          </button>
        </div>
      </div>
    </aside>
  );
}

// ── Answer ────────────────────────────────────────────────────────

function AnswerCard({ r }: { r: QueryResponse }) {
  return (
    <article aria-label="Answer"
             className="card p-6 animate-slide-up">
      <div className="flex items-center justify-between mb-5">
        <ConfidenceBadge label={r.confidence_label} score={r.confidence_score} />
        <span className="text-xs text-ink-tertiary font-medium">
          {r.chunks_used} chunks · {r.response_ms}ms
        </span>
      </div>

      {r.insufficient_context && (
        <div role="alert"
             className="mb-5 px-4 py-3 rounded-lg bg-warning-bg border
                        border-warning-border text-sm text-warning-text">
          {r.warning_message}
        </div>
      )}

      <p className="text-md text-ink leading-[1.75] whitespace-pre-wrap">
        {r.answer}
      </p>

      <SourcePanel citations={r.citations} />

      <div className="mt-5 pt-4 border-t border-edge flex gap-3 text-2xs
                      text-ink-disabled font-medium">
        <span className="font-mono">{r.namespace}</span>
        <span>·</span>
        <span>{r.citations.length} source{r.citations.length !== 1 ? "s" : ""}</span>
      </div>
    </article>
  );
}

function AnswerSkeleton() {
  return (
    <div role="status" aria-label="Generating answer…" className="card p-6 space-y-3">
      <Skeleton className="h-5 w-24 mb-5" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-11/12" />
      <Skeleton className="h-4 w-4/5" />
      <Skeleton className="h-4 w-3/4" />
      <div className="pt-4 space-y-2">
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────

export default function QueryInterface() {
  const { user, credential, signOut, refreshUser } = useAuth();
  const [namespace, setNamespace] = useState<Namespace>("kubernetes-docs");
  const [question,  setQuestion]  = useState("");
  const [status,    setStatus]    = useState<QueryStatus>({ type: "idle" });
  const ref = useRef<HTMLTextAreaElement>(null);

  const remaining = user?.queries_remaining ?? 0;
  const limit     = user?.query_limit       ?? 3;
  const busy      = status.type === "loading";
  const canAsk    = question.trim().length >= 3 && remaining > 0 && !busy;

  const submit = useCallback(async () => {
    if (!canAsk || !credential) return;
    setStatus({ type: "loading" });
    try {
      const data = await api.query.submit(question.trim(), namespace, credential);
      setStatus({ type: "success", data });
      await refreshUser();
    } catch (err) {
      setStatus({
        type:    "error",
        message: err instanceof ApiError ? err.message : "Something went wrong.",
      });
    }
  }, [canAsk, credential, question, namespace, refreshUser]);

  const onKey = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault(); void submit();
    }
  }, [submit]);

  if (!user) return null;

  const activeLabel = NAMESPACES.find(n => n.value === namespace)?.label ?? "Query";

  return (
    <div className="flex h-screen bg-surface-subtle overflow-hidden">
      <Sidebar
        namespace={namespace}
        onNamespace={ns => { setNamespace(ns); setStatus({ type: "idle" }); }}
        queriesRemaining={remaining}
        queryLimit={limit}
        user={user}
        onSignOut={signOut}
      />

      <main className="relative flex-1 flex flex-col min-w-0">

        {/* Top bar */}
        <div className="h-[52px] bg-surface border-b border-edge flex items-center
                        px-6 gap-4 flex-shrink-0">
          <h1 className="text-base font-semibold text-ink flex-1">{activeLabel}</h1>
          {status.type === "success" && (
            <button
              onClick={() => { setStatus({ type: "idle" }); setQuestion(""); }}
              className="text-xs font-medium text-ink-secondary hover:text-ink
                         border border-edge hover:border-edge-strong
                         px-3 py-1.5 rounded-lg bg-surface hover:bg-surface-muted
                         transition-all duration-150">
              ← New query
            </button>
          )}
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-[680px] mx-auto px-6 py-8 space-y-5">

            {/* Input */}
            <div className={`bg-surface rounded-xl border shadow-xs
                             transition-shadow duration-200 ${
              busy
                ? "border-brand shadow-focus"
                : "border-edge hover:border-edge-strong"
            }`}>
              <label htmlFor="q" className="sr-only">Your question</label>
              <textarea
                id="q" ref={ref}
                value={question}
                onChange={e => setQuestion(e.target.value)}
                onKeyDown={onKey}
                placeholder="Ask anything about your engineering documentation…"
                disabled={remaining === 0 || busy}
                rows={3}
                className="w-full px-4 pt-4 pb-3 bg-transparent text-md
                           text-ink placeholder:text-ink-disabled border-none
                           outline-none disabled:opacity-50"
                aria-describedby="q-hint"
              />
              <div className="flex items-center justify-between px-4 pb-4">
                <p id="q-hint" className="text-xs text-ink-tertiary">
                  {remaining === 0 ? "Query limit reached" : "⌘ Return to submit"}
                </p>
                <button
                  onClick={() => void submit()}
                  disabled={!canAsk}
                  aria-busy={busy}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg
                             text-sm font-semibold text-white bg-brand hover:bg-brand-hover
                             active:scale-95 disabled:opacity-35 disabled:cursor-not-allowed
                             transition-all duration-150 shadow-xs">
                  {busy && <Spinner size={12} />}
                  {busy ? "Thinking…" : "Ask"}
                </button>
              </div>
            </div>

            {/* States */}
            {status.type === "idle" && (
              <div className="animate-fade-in">
                <EmptyState
                  icon={
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                      <circle cx="11" cy="11" r="8"/>
                      <path d="m21 21-4.35-4.35"/>
                    </svg>
                  }
                  title="Ready to search"
                  subtitle="Questions are answered using only indexed documentation. Every claim is attributed to its exact source."
                />
                <div className="mt-2 space-y-2">
                  <p className="label-caps text-center mb-4">Try an example</p>
                  {EXAMPLES.map(q => (
                    <button key={q}
                      onClick={() => { setQuestion(q); ref.current?.focus(); }}
                      className="w-full text-left px-4 py-3.5 rounded-xl bg-surface
                                 border border-edge hover:border-edge-strong
                                 hover:shadow-xs text-sm text-ink-secondary
                                 hover:text-ink transition-all duration-150 font-medium">
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {status.type === "loading" && <AnswerSkeleton />}

            {status.type === "error" && (
              <div role="alert"
                   className="px-5 py-4 rounded-xl bg-danger-bg border
                              border-danger-border text-sm text-danger-text
                              animate-fade-in">
                {status.message}
              </div>
            )}

            {status.type === "success" && <AnswerCard r={status.data} />}
          </div>
        </div>

        <Footer className="absolute bottom-4 right-6" />
      </main>
    </div>
  );
}
